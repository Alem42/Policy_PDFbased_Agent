import { useEffect, useMemo, useState } from "react";
import {
  Box,
  Card,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  ListSubheader,
  FormControl,
  Alert,
  Chip,
  Skeleton,
  Menu,
  Divider,
  Pagination,
  Popover,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Autocomplete,
  Tooltip,
} from "@mui/material";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import dayjs from "dayjs";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { useSearchParams } from "react-router-dom";
import {
  deleteDocument,
  getDocumentChunks,
  getDocumentDetail,
  getProcessingStatus,
  getTaxonomy,
  openDocumentFile,
  rescanFile,
  searchDocuments,
  updateDocument,
} from "../api";
import DocumentDrawer from "../components/DocumentDrawer";
import DocumentUpload from "../components/DocumentUpload";
import { formatDate, formatSize } from "../utils/format";

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "ready", label: "Ready" },
  { value: "failed", label: "Failed" },
  { value: "uploaded", label: "Uploaded" },
  { value: "parsed", label: "Parsed" },
  { value: "annotated", label: "Annotated" },
];

const SORT_OPTIONS = [
  { value: "uploaded_desc", label: "Newest first" },
  { value: "name_asc", label: "Filename A-Z" },
  { value: "year_desc", label: "Year desc" },
  { value: "chunks_desc", label: "Most chunks" },
];

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
const SEARCH_PARAM_DEFAULTS = {
  q: "",
  status: "all",
  policy_area: "all",
  country_region: "all",
  source_type: "all",
  sort: "uploaded_desc",
  page: 1,
  page_size: 20,
};

const filterSelectSx = { minWidth: 140, "& .MuiSelect-select": { py: "10px" } };

const TERMINAL_PROCESSING = new Set(["ready", "indexed", "failed"]);

function processingColor(status) {
  if (status === "ready" || status === "indexed") return "success.main";
  if (status === "failed") return "error.main";
  return "text.secondary";
}

// Self-contained processing status for one row. Renders the list value by
// default; when `rescanSignal` changes (a rescan was triggered for THIS doc), it
// polls only this document's status until it settles — updating just this cell,
// with no whole-table refetch or flicker. On completion it pulls fresh
// pages/chunks once.
function ProcessingCell({ document, rescanSignal }) {
  const [live, setLive] = useState({
    status: document.status,
    pages: document.page_count || 0,
    chunks: document.chunk_count || 0,
  });

  // Re-sync if the underlying row data changes (e.g. a normal list refetch).
  useEffect(() => {
    setLive({
      status: document.status,
      pages: document.page_count || 0,
      chunks: document.chunk_count || 0,
    });
  }, [document.status, document.page_count, document.chunk_count]);

  useEffect(() => {
    if (!rescanSignal) return undefined;
    let cancelled = false;
    let timer = null;
    setLive((prev) => ({ ...prev, status: "processing" }));
    async function tick() {
      try {
        const result = await getProcessingStatus(document.id);
        if (cancelled) return;
        setLive((prev) => ({ ...prev, status: result.status || prev.status }));
        if (TERMINAL_PROCESSING.has(result.status)) {
          try {
            const detail = await getDocumentDetail(document.id);
            if (!cancelled) {
              setLive({
                status: detail.status || result.status,
                pages: detail.page_count || 0,
                chunks: detail.chunk_count || 0,
              });
            }
          } catch {
            /* keep the polled status */
          }
          return; // settled -> stop polling
        }
      } catch {
        /* transient error: keep last known status */
      }
      if (!cancelled) timer = setTimeout(tick, 2000);
    }
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [rescanSignal, document.id]);

  return (
    <>
      <Typography variant="body2" sx={{ fontWeight: 800, color: processingColor(live.status) }}>
        {live.status || "unknown"}
      </Typography>
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        {live.pages} pages
      </Typography>
      <Typography variant="body2" sx={{ color: "text.secondary" }}>
        {live.chunks} chunks
      </Typography>
    </>
  );
}

const EMPTY_EDIT_FORM = {
  title: "",
  summary: "",
  source_type: "",
  source_organisation: "",
  country_region: "",
  language: "",
  publication_date: "",
  year: "",
  policy_areas: [],
  keywords: [],
};

export default function LibraryPage({
  documents,
  user,
  onRefresh,
  onRescan,
  onDocumentsChanged,
  onNavigate,
  contextSourceIds = [],
  onAddSource,
  onRemoveSource,
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") || "";
  const requestedStatus = searchParams.get("status") || "all";
  const statusFilter = STATUS_OPTIONS.some(({ value }) => value === requestedStatus)
    ? requestedStatus
    : "all";
  const areaFilter = searchParams.get("policy_area") || "all";
  const regionFilter = searchParams.get("country_region") || "all";
  const typeFilter = searchParams.get("source_type") || "all";
  const requestedSort = searchParams.get("sort") || "uploaded_desc";
  const sortBy = SORT_OPTIONS.some(({ value }) => value === requestedSort)
    ? requestedSort
    : "uploaded_desc";
  const requestedPage = Number.parseInt(searchParams.get("page") || "1", 10);
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const requestedPageSize = Number.parseInt(searchParams.get("page_size") || "20", 10);
  const pageSize = PAGE_SIZE_OPTIONS.includes(requestedPageSize) ? requestedPageSize : 20;
  const [pageData, setPageData] = useState({ items: [], total: 0, pages: 0 });
  const [searchLoading, setSearchLoading] = useState(true);
  const [searchVersion, setSearchVersion] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [chunks, setChunks] = useState(null);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [openChunkId, setOpenChunkId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Per-row rescan trigger: bumping a doc's counter makes its ProcessingCell poll.
  const [rescanSignals, setRescanSignals] = useState({});

  // Re-fetch documents when the embedding model changes (so any model-derived
  // detail refreshes). The Processing status itself is model-independent.
  useEffect(() => {
    function onConfig() {
      setSearchVersion((current) => current + 1);
    }
    window.addEventListener("embedding-config-changed", onConfig);
    return () => window.removeEventListener("embedding-config-changed", onConfig);
  }, []);

  const [moreMenuAnchor, setMoreMenuAnchor] = useState(null);
  const [moreMenuDocument, setMoreMenuDocument] = useState(null);
  const [addedPopover, setAddedPopover] = useState({ anchorEl: null, document: null, success: true });
  const [editDialog, setEditDialog] = useState({ open: false, document: null, form: EMPTY_EDIT_FORM, saving: false });
  const [deleteDialog, setDeleteDialog] = useState({ open: false, document: null });
  const [taxonomy, setTaxonomy] = useState([]); // [{ parent, children: [] }]

  function updateSearchParams(updates, { replace = false } = {}) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(updates)) {
        if (value === SEARCH_PARAM_DEFAULTS[key] || value === "" || value === "all") {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      }
      return next;
    }, { replace });
  }

  const policyAreas = useMemo(
    () =>
      [...new Set(documents.flatMap((document) => document.policy_areas || []))]
        .filter(Boolean)
        .sort(),
    [documents],
  );
  const regions = useMemo(
    () =>
      [...new Set(documents.map((document) => document.country_region))]
        .filter(Boolean)
        .sort(),
    [documents],
  );
  const sourceTypes = useMemo(
    () =>
      [...new Set(documents.map((document) => document.source_type))]
        .filter(Boolean)
        .sort(),
    [documents],
  );

  // Load the two-level taxonomy once; the filter bar + edit dialog group by parent.
  useEffect(() => {
    getTaxonomy()
      .then((result) => setTaxonomy(result.groups || []))
      .catch(() => setTaxonomy([]));
  }, []);

  // Flat leaf labels (taxonomy order) for the edit autocomplete options.
  const taxonomyLeaves = useMemo(
    () => taxonomy.flatMap((group) => group.children || []),
    [taxonomy],
  );

  // Leaf -> parent, so the autocomplete can group free-form values too.
  const parentOfLeaf = useMemo(() => {
    const map = {};
    for (const group of taxonomy) {
      for (const child of group.children || []) map[child] = group.parent;
    }
    return map;
  }, [taxonomy]);

  // Any leaf present on documents but not in the taxonomy (legacy tags) so the
  // filter never hides an existing value.
  const uncategorisedAreas = useMemo(
    () => policyAreas.filter((area) => !(area in parentOfLeaf)),
    [policyAreas, parentOfLeaf],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearchLoading(true);
      setError("");
      try {
        const result = await searchDocuments(
          {
            q: query.trim(),
            status: statusFilter,
            policy_area: areaFilter,
            country_region: regionFilter,
            source_type: typeFilter,
            sort: sortBy,
            page,
            page_size: pageSize,
          },
          { signal: controller.signal },
        );
        if (result.pages > 0 && page > result.pages) {
          updateSearchParams({ page: result.pages }, { replace: true });
          return;
        }
        setPageData(result);
      } catch (searchError) {
        if (searchError.name !== "AbortError") setError(searchError.message);
      } finally {
        if (!controller.signal.aborted) setSearchLoading(false);
      }
    }, 300);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [
    areaFilter,
    page,
    pageSize,
    query,
    regionFilter,
    searchVersion,
    sortBy,
    statusFilter,
    typeFilter,
    user,
  ]);

  function refreshSearch() {
    setSearchVersion((current) => current + 1);
  }

  async function handleDocumentsChanged(documentIds) {
    await onDocumentsChanged(documentIds);
    refreshSearch();
  }

  function handleDelete(document) {
    setDeleteDialog({ open: true, document });
  }

  async function handleDeleteConfirm() {
    const { document } = deleteDialog;
    setDeleteDialog({ open: false, document: null });
    setBusy(true);
    setError("");
    try {
      await deleteDocument(document.id);
      if (selected?.id === document.id) closeDrawer();
      await handleDocumentsChanged();
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenSource(document) {
    setBusy(true);
    setError("");
    try {
      await openDocumentFile(document.id);
    } catch (sourceError) {
      setError(sourceError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleGovernanceUpdate(document, updates) {
    setBusy(true);
    setError("");
    try {
      await updateDocument(document.id, updates);
      await handleDocumentsChanged();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusy(false);
    }
  }

  function openEditDialog(document) {
    setEditDialog({
      open: true,
      document,
      form: {
        title: document.title || "",
        summary: document.summary || "",
        source_type: document.source_type || "",
        source_organisation: document.source_organisation || "",
        country_region: document.country_region || "",
        language: document.language || "",
        publication_date: document.publication_date ? String(document.publication_date).slice(0, 10) : "",
        year: document.year ?? "",
        policy_areas: document.policy_areas || [],
        keywords: document.keywords || [],
      },
      saving: false,
    });
  }

  function closeEditDialog() {
    setEditDialog({ open: false, document: null, form: EMPTY_EDIT_FORM, saving: false });
  }

  function updateEditField(field, value) {
    setEditDialog((state) => ({ ...state, form: { ...state.form, [field]: value } }));
  }

  async function handleSaveEdit() {
    const { document, form } = editDialog;
    setEditDialog((state) => ({ ...state, saving: true }));
    setError("");
    try {
      await updateDocument(document.id, {
        title: form.title,
        summary: form.summary,
        source_type: form.source_type,
        source_organisation: form.source_organisation,
        country_region: form.country_region,
        language: form.language,
        publication_date: form.publication_date || null,
        year: form.year === "" ? null : Number(form.year),
        policy_areas: form.policy_areas,
        keywords: form.keywords,
      });
      closeEditDialog();
      await handleDocumentsChanged();
    } catch (updateError) {
      setError(updateError.message);
      setEditDialog((state) => ({ ...state, saving: false }));
    }
  }

  async function handleDetail(document) {
    setError("");
    // Open the drawer immediately with a skeleton; metadata and chunks both
    // fill in afterwards once their fetches resolve. `drawerOpen` is a single
    // dedicated flag set once here and only cleared by closeDrawer(), so the
    // drawer never flickers shut while `selected`/`detailLoading` are
    // updating in between.
    setSelected(null);
    setChunks(null);
    setOpenChunkId(null);
    setDetailLoading(true);
    setDrawerOpen(true);

    let detail;
    try {
      detail = await getDocumentDetail(document.id);
    } catch (detailError) {
      setError(detailError.message);
      setDetailLoading(false);
      return;
    }

    setSelected(detail);
    setDetailLoading(false);

    if (document.status === "ready") {
      setChunksLoading(true);
      try {
        setChunks(await getDocumentChunks(document.id));
      } catch (chunkError) {
        setError(chunkError.message);
      } finally {
        setChunksLoading(false);
      }
    }
  }

  function openMoreMenu(event, document) {
    setMoreMenuAnchor(event.currentTarget);
    setMoreMenuDocument(document);
  }

  function closeMoreMenu() {
    setMoreMenuAnchor(null);
  }

  function runMoreAction(action) {
    const document = moreMenuDocument;
    closeMoreMenu();
    if (document) action(document);
  }

  async function handleRescanFile(document) {
    setError("");
    try {
      await rescanFile(document.id);
      // Signal this row's ProcessingCell to start polling its own status.
      setRescanSignals((prev) => ({ ...prev, [document.id]: (prev[document.id] || 0) + 1 }));
    } catch (rescanError) {
      setError(rescanError.message);
    }
  }

  function closeDrawer() {
    setDrawerOpen(false);
    setSelected(null);
    setDetailLoading(false);
    setChunks(null);
    setChunksLoading(false);
    setOpenChunkId(null);
  }

  function handleAddToChat(event, document) {
    try {
      onAddSource(document.id, document);
      setAddedPopover({ anchorEl: event.currentTarget, document, success: true });
    } catch (addError) {
      setAddedPopover({ anchorEl: event.currentTarget, document, success: false, error: addError.message });
    }
  }

  function closeAddedPopover() {
    // Only clear anchorEl (which drives `open`) -- keep success/error/document
    // as-is so the content doesn't flip to the "failed" state while the
    // Popover is still fading out.
    setAddedPopover((state) => ({ ...state, anchorEl: null }));
  }

  function handleGoToChat() {
    closeAddedPopover();
    onNavigate("chat");
  }

  return (
    <Box component="section">
      {/* Page heading */}
      <Box
        sx={{
          display: "flex",
          maxWidth: "none",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "20px",
          flexWrap: "wrap",
          py: "54px 0 28px",
          pt: "54px",
          pb: "28px",
        }}
      >
        <Box>
        <Typography variant="subtitle2">
          {user?.role === "admin" ? "Admin Workspace" : "Policy library"}
        </Typography>
        <Typography variant="h1">
          {user?.role === "admin" ? "Document Management" : "Document Library"}
        </Typography>
        <Typography variant="body1" sx={{ mt: "18px", color: "#63706a" }}>
          {user?.role === "admin"
            ? "Manage uploaded documents, inspect metadata, and review retrieval chunks."
            : "Browse available documents, inspect metadata, and add relevant sources to your chat context."}
        </Typography>
      </Box>
      </Box>

      {user?.role === "admin" && <DocumentUpload compact onUploaded={handleDocumentsChanged} />}

      {/* Filter bar */}
      <Card
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 1,
          p: 1.5,
          mb: 2,
          alignItems: "center",
        }}
      >
        <TextField
          value={query}
          onChange={(event) => {
            updateSearchParams({ q: event.target.value, page: 1 }, { replace: true });
          }}
          placeholder="Search filename, title, region, policy area, keywords"
          size="small"
          sx={{ minWidth: 220, flex: 1 }}
        />
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={statusFilter} onChange={(event) => {
            updateSearchParams({ status: event.target.value, page: 1 });
          }}>
            {STATUS_OPTIONS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ ...filterSelectSx, minWidth: 180, maxWidth: 220 }}>
          {/* Grouped by parent category; selecting a leaf filters by that subcategory. */}
          <Select
            value={areaFilter}
            onChange={(event) => {
              updateSearchParams({ policy_area: event.target.value, page: 1 });
            }}
            // Cap the popup height/width so it stays a compact scrollable dropdown.
            MenuProps={{ PaperProps: { style: { maxHeight: 300, maxWidth: 280 } } }}
            sx={{ "& .MuiSelect-select": { overflow: "hidden", textOverflow: "ellipsis" } }}
          >
            <MenuItem value="all">All policy areas</MenuItem>
            {taxonomy.flatMap((group) => [
              <ListSubheader key={`h-${group.parent}`}>{group.parent}</ListSubheader>,
              ...(group.children || []).map((child) => (
                <MenuItem key={child} value={child} sx={{ pl: 3 }}>{child}</MenuItem>
              )),
            ])}
            {uncategorisedAreas.length > 0 && (
              <ListSubheader key="h-uncat">Uncategorised</ListSubheader>
            )}
            {uncategorisedAreas.map((area) => (
              <MenuItem key={area} value={area} sx={{ pl: 3 }}>{area}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={regionFilter} onChange={(event) => {
            updateSearchParams({ country_region: event.target.value, page: 1 });
          }}>
            <MenuItem value="all">All regions</MenuItem>
            {regions.map((region) => (
              <MenuItem key={region} value={region}>{region}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={typeFilter} onChange={(event) => {
            updateSearchParams({ source_type: event.target.value, page: 1 });
          }}>
            <MenuItem value="all">All source types</MenuItem>
            {sourceTypes.map((sourceType) => (
              <MenuItem key={sourceType} value={sourceType}>{sourceType}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={sortBy} onChange={(event) => {
            updateSearchParams({ sort: event.target.value, page: 1 });
          }}>
            {SORT_OPTIONS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Document table */}
      <Card sx={{ p: 0, overflow: "hidden" }}>
        {/* Table header */}
        <Box
          sx={{
            display: { xs: "none", md: "grid" },
            gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 0.9fr) minmax(110px, 0.5fr) minmax(360px, auto)",
            gap: 2,
            px: 3,
            py: 1.5,
            borderBottom: "1px solid #e2e5df",
            bgcolor: "#f9faf7",
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 800 }}>Document</Typography>
          <Typography variant="body2" sx={{ fontWeight: 800 }}>Metadata</Typography>
          <Typography variant="body2" sx={{ fontWeight: 800 }}>Processing</Typography>
          <Typography variant="body2" sx={{ fontWeight: 800 }}>Actions</Typography>
        </Box>

        {searchLoading ? (
          <Box sx={{ p: 2 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <Box
                key={i}
                sx={{
                  display: { xs: "block", lg: "grid" },
                  gridTemplateColumns: "minmax(220px, 1.15fr) minmax(240px, 0.9fr) minmax(120px, 0.45fr) minmax(330px, auto)",
                  columnGap: 3,
                  rowGap: 2,
                  px: 3,
                  py: 2,
                  borderBottom: "1px solid #eaece5",
                }}
              >
                <Box>
                  <Skeleton variant="text" width="70%" height={20} />
                  <Skeleton variant="text" width="50%" height={16} />
                  <Skeleton variant="text" width="40%" height={16} />
                </Box>
                <Box>
                  <Skeleton variant="text" width="60%" height={16} />
                  <Skeleton variant="text" width="50%" height={16} />
                  <Skeleton variant="text" width="40%" height={16} />
                </Box>
                <Box>
                  <Skeleton variant="text" width={80} height={20} />
                  <Skeleton variant="text" width={60} height={16} />
                </Box>
                <Box sx={{ display: "flex", gap: 1, mt: { xs: 1, lg: 0 }, justifySelf: "end" }}>
                  <Skeleton variant="rounded" width={110} height={40} />
                  <Skeleton variant="rounded" width={76} height={40} />
                  <Skeleton variant="rounded" width={88} height={40} />
                  <Skeleton variant="rounded" width={76} height={40} />
                </Box>
              </Box>
            ))}
          </Box>
        ) : pageData.items.length === 0 ? (
          <Typography sx={{ py: 4, textAlign: "center", color: "text.secondary" }}>
            No matching documents.
          </Typography>
        ) : (
          pageData.items.map((document) => (
            <Box
              key={document.id}
              sx={{
                display: { xs: "block", lg: "grid" },
                gridTemplateColumns: "minmax(220px, 1.15fr) minmax(240px, 0.9fr) minmax(120px, 0.45fr) minmax(330px, auto)",
                columnGap: 3,
                rowGap: 2,
                px: 3,
                py: 2,
                borderBottom: "1px solid #eaece5",
                "&:last-child": { borderBottom: "none" },
                "&:hover": { bgcolor: "#fafaf7" },
              }}
            >
              {/* Document cell */}
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  component="strong"
                  sx={{ fontWeight: 700, display: "block", overflowWrap: "anywhere" }}
                >
                  {document.title || document.name}
                </Typography>
                <Tooltip title={document.original_filename || document.name || ""} arrow>
                  <Typography
                    variant="caption"
                    noWrap
                    sx={{
                      color: "text.secondary",
                      display: "block",
                      maxWidth: "100%",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    Original file: {document.original_filename || document.name}
                  </Typography>
                </Tooltip>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {formatSize(document.size)} - {formatDate(document.uploaded_at)}
                </Typography>
              </Box>

              {/* Metadata cell */}
              <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.country_region || "Unknown region"}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.source_type || "Unclassified source"}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.source_organisation || "Unknown organisation"}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.language || "Unknown language"}
                </Typography>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
                  {(document.policy_areas || []).slice(0, 3).map((area) => (
                    <Chip key={area} label={area} size="small" variant="outlined" />
                  ))}
                </Box>
              </Box>

              {/* Processing cell */}
              <Box sx={{ minWidth: 0 }}>
                <ProcessingCell
                  document={document}
                  rescanSignal={rescanSignals[document.id] || 0}
                />
                {user?.role === "admin" && (
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    {document.approved ? "approved" : "not approved"} / {document.access_level}
                  </Typography>
                )}
              </Box>

              {/* Actions cell */}
              <Box
                sx={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 1,
                  alignItems: "center",
                  justifyContent: { xs: "flex-start", lg: "flex-end" },
                  justifySelf: { lg: "end" },
                  mt: { xs: 2, lg: 0 },
                  "& .MuiButton-root": {
                    minHeight: 40,
                  },
                }}
              >
                {!user ? (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={busy}
                    onClick={() => window.alert("Log in to add")}
                    sx={{
                      bgcolor: "#8a938e",
                      "&:hover": { bgcolor: "#747d78" },
                    }}
                  >
                    Add to chat
                  </Button>
                ) : contextSourceIds.includes(document.id) ? (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={busy}
                    onClick={() => onRemoveSource(document.id)}
                    sx={{ color: "error.main", borderColor: "error.main", minWidth: 108 }}
                  >
                    Remove
                  </Button>
                ) : (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={busy}
                    onClick={(event) => handleAddToChat(event, document)}
                    sx={{ minWidth: 108 }}
                  >
                    Add to chat
                  </Button>
                )}
                <Button size="small" variant="outlined" disabled={busy} onClick={() => handleDetail(document)}>
                  Details
                </Button>
                {user?.role === "admin" && (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={busy}
                    onClick={() =>
                      handleGovernanceUpdate(document, { approved: !document.approved })
                    }
                  >
                    {document.approved ? "Unapprove" : "Approve"}
                  </Button>
                )}
                <Button
                  size="small"
                  variant="outlined"
                  disabled={busy}
                  endIcon={<KeyboardArrowDownIcon />}
                  onClick={(event) => openMoreMenu(event, document)}
                >
                  More
                </Button>
              </Box>
            </Box>
          ))
        )}
      </Card>

      {!searchLoading && pageData.total > 0 && (
        <Card
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 2,
            flexWrap: "wrap",
            mt: 2,
            px: 2,
            py: 1.25,
          }}
        >
          <Typography variant="body2" color="text.secondary">
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, pageData.total)} of{" "}
            {pageData.total} document{pageData.total === 1 ? "" : "s"}
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography variant="body2" color="text.secondary">
                Per page
              </Typography>
              <FormControl size="small">
                <Select
                  value={pageSize}
                  onChange={(event) => {
                    updateSearchParams({ page_size: Number(event.target.value), page: 1 });
                  }}
                  inputProps={{ "aria-label": "Documents per page" }}
                  sx={{
                    minWidth: 76,
                    color: "primary.main",
                    fontWeight: 800,
                    "& .MuiSelect-select": { py: "7px", pl: 1.5 },
                  }}
                >
                  {PAGE_SIZE_OPTIONS.map((option) => (
                    <MenuItem key={option} value={option}>{option}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
            <Pagination
              count={pageData.pages}
              page={page}
              onChange={(_, nextPage) => updateSearchParams({ page: nextPage })}
              color="primary"
              shape="rounded"
            />
          </Box>
        </Card>
      )}

      <Menu anchorEl={moreMenuAnchor} open={Boolean(moreMenuAnchor)} onClose={closeMoreMenu}>
        <MenuItem onClick={() => runMoreAction(handleOpenSource)}>Open source</MenuItem>
        {user?.role === "admin" && <Divider />}
        {user?.role === "admin" && (
          <MenuItem onClick={() => runMoreAction(openEditDialog)}>Edit</MenuItem>
        )}
        {user?.role === "admin" && (
          <MenuItem onClick={() => runMoreAction(handleRescanFile)}>Rescan file</MenuItem>
        )}
        {user?.role === "admin" && (
          <MenuItem
            onClick={() =>
              runMoreAction((document) =>
                handleGovernanceUpdate(document, {
                  access_level: document.access_level === "public" ? "private" : "public",
                }),
              )
            }
          >
            Make {moreMenuDocument?.access_level === "public" ? "private" : "public"}
          </MenuItem>
        )}
        {user?.role === "admin" && (
          <MenuItem sx={{ color: "error.main" }} onClick={() => runMoreAction(handleDelete)}>
            Delete
          </MenuItem>
        )}
      </Menu>

      {/* "Added to chat" confirmation bubble */}
      <Popover
        open={Boolean(addedPopover.anchorEl)}
        anchorEl={addedPopover.anchorEl}
        onClose={closeAddedPopover}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        transformOrigin={{ vertical: "top", horizontal: "center" }}
        slotProps={{ paper: { sx: { mt: 1, borderRadius: 2 } } }}
      >
        <Box sx={{ px: 1.5, py: 1, display: "flex", flexDirection: "column", gap: 0.75, minWidth: 160 }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.5,
              color: addedPopover.success ? "success.main" : "error.main",
            }}
          >
            {addedPopover.success ? (
              <CheckCircleIcon sx={{ fontSize: 16 }} />
            ) : (
              <ErrorIcon sx={{ fontSize: 16 }} />
            )}
            <Typography variant="caption" sx={{ fontWeight: 700, whiteSpace: "nowrap" }}>
              {addedPopover.success ? "Added to chat" : addedPopover.error || "Failed to add"}
            </Typography>
          </Box>
          <Button
            size="small"
            variant="contained"
            fullWidth
            onClick={handleGoToChat}
            sx={{ py: 0.4, fontSize: 12, minHeight: 0 }}
          >
            Go to chat
          </Button>
        </Box>
      </Popover>

      {/* Edit document metadata dialog */}
      <Dialog open={editDialog.open} onClose={closeEditDialog} maxWidth="md" fullWidth>
      <LocalizationProvider dateAdapter={AdapterDayjs}>
        <DialogTitle>Edit document</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, pt: 1 }}>
            <TextField
              label="Title"
              fullWidth
              size="small"
              value={editDialog.form.title}
              onChange={(e) => updateEditField("title", e.target.value)}
            />
            <TextField
              label="Summary"
              fullWidth
              multiline
              rows={3}
              size="small"
              value={editDialog.form.summary}
              onChange={(e) => updateEditField("summary", e.target.value)}
            />
            <TextField
              label="Source type"
              size="small"
              sx={{ flex: "1 1 45%" }}
              value={editDialog.form.source_type}
              onChange={(e) => updateEditField("source_type", e.target.value)}
            />
            <TextField
              label="Source organisation"
              size="small"
              sx={{ flex: "1 1 45%" }}
              value={editDialog.form.source_organisation}
              onChange={(e) => updateEditField("source_organisation", e.target.value)}
            />
            <TextField
              label="Region"
              size="small"
              sx={{ flex: "1 1 45%" }}
              value={editDialog.form.country_region}
              onChange={(e) => updateEditField("country_region", e.target.value)}
            />
            <TextField
              label="Language"
              size="small"
              sx={{ flex: "1 1 45%" }}
              value={editDialog.form.language}
              onChange={(e) => updateEditField("language", e.target.value)}
            />
            <TextField
              label="Year"
              type="number"
              size="small"
              sx={{ flex: "1 1 45%" }}
              value={editDialog.form.year}
              onChange={(e) => updateEditField("year", e.target.value)}
            />
            <DatePicker
              label="Publication date"
              value={editDialog.form.publication_date ? dayjs(editDialog.form.publication_date) : null}
              onChange={(newValue) =>
                updateEditField(
                  "publication_date",
                  newValue && newValue.isValid() ? newValue.format("YYYY-MM-DD") : "",
                )
              }
              slotProps={{ textField: { size: "small" } }}
              sx={{ flex: "1 1 45%" }}
            />
            <Autocomplete
              multiple
              freeSolo
              fullWidth
              size="small"
              options={taxonomyLeaves}
              groupBy={(option) => parentOfLeaf[option] || "Other"}
              value={editDialog.form.policy_areas}
              onChange={(_, value) => updateEditField("policy_areas", value)}
              renderValue={(value, getItemProps) =>
                value.map((option, index) => {
                  const { key, ...itemProps } = getItemProps({ index });
                  return <Chip key={key} label={option} size="small" {...itemProps} />;
                })
              }
              renderInput={(params) => (
                <TextField {...params} label="Policy areas" placeholder="Pick a subcategory or type" />
              )}
              sx={{ width: "100%" }}
            />
            <Autocomplete
              multiple
              freeSolo
              fullWidth
              size="small"
              options={[]}
              value={editDialog.form.keywords}
              onChange={(_, value) => updateEditField("keywords", value)}
              renderValue={(value, getItemProps) =>
                value.map((option, index) => {
                  const { key, ...itemProps } = getItemProps({ index });
                  return <Chip key={key} label={option} size="small" {...itemProps} />;
                })
              }
              renderInput={(params) => (
                <TextField {...params} label="Keywords" placeholder="Type and press enter" />
              )}
              sx={{ width: "100%" }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEditDialog} disabled={editDialog.saving}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleSaveEdit} disabled={editDialog.saving}>
            {editDialog.saving ? "Saving..." : "Save"}
          </Button>
        </DialogActions>
      </LocalizationProvider>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteDialog.open} onClose={() => setDeleteDialog({ open: false, document: null })}>
        <DialogTitle>Delete document?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete &ldquo;{deleteDialog.document?.name}&rdquo;? This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, document: null })}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDeleteConfirm}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      <DocumentDrawer
        open={drawerOpen}
        detail={selected}
        detailLoading={detailLoading}
        chunks={chunks}
        chunksLoading={chunksLoading}
        openChunkId={openChunkId}
        onToggleChunk={(chunkId) => setOpenChunkId(openChunkId === chunkId ? null : chunkId)}
        onClose={closeDrawer}
      />
    </Box>
  );
}
