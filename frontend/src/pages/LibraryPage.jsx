import { useMemo, useState } from "react";
import {
  Box,
  Card,
  Typography,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  Alert,
  Chip,
  Skeleton,
  Menu,
  Divider,
} from "@mui/material";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import {
  deleteDocument,
  getDocumentChunks,
  getDocumentDetail,
  openDocumentFile,
  updateDocument,
} from "../api";
import DocumentDrawer from "../components/DocumentDrawer";
import DocumentUpload from "../components/DocumentUpload";
import { asText, formatDate, formatSize } from "../utils/format";

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

const filterSelectSx = { minWidth: 140, "& .MuiSelect-select": { py: "10px" } };

export default function LibraryPage({
  documents,
  loading,
  user,
  onRefresh,
  onRescan,
  onDocumentsChanged,
  contextSourceIds = [],
  onAddSource,
  onRemoveSource,
}) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [areaFilter, setAreaFilter] = useState("all");
  const [regionFilter, setRegionFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortBy, setSortBy] = useState("uploaded_desc");
  const [selected, setSelected] = useState(null);
  const [chunks, setChunks] = useState(null);
  const [openChunkId, setOpenChunkId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [moreMenuAnchor, setMoreMenuAnchor] = useState(null);
  const [moreMenuDocument, setMoreMenuDocument] = useState(null);

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

  const filteredDocuments = useMemo(() => {
    const cleanQuery = query.trim().toLowerCase();
    const filtered = documents.filter((document) => {
      const searchText = [
        document.name,
        document.title,
        document.summary,
        document.country_region,
        document.source_type,
        document.year,
        asText(document.policy_areas),
        asText(document.keywords),
      ]
        .join(" ")
        .toLowerCase();

      return (
        (!cleanQuery || searchText.includes(cleanQuery)) &&
        (statusFilter === "all" || document.status === statusFilter) &&
        (areaFilter === "all" || (document.policy_areas || []).includes(areaFilter)) &&
        (regionFilter === "all" || document.country_region === regionFilter) &&
        (typeFilter === "all" || document.source_type === typeFilter)
      );
    });

    return [...filtered].sort((first, second) => {
      if (sortBy === "name_asc") return first.name.localeCompare(second.name);
      if (sortBy === "year_desc") return (second.year || 0) - (first.year || 0);
      if (sortBy === "chunks_desc") return (second.chunk_count || 0) - (first.chunk_count || 0);
      return (second.modified_at || 0) - (first.modified_at || 0);
    });
  }, [areaFilter, documents, query, regionFilter, sortBy, statusFilter, typeFilter]);

  async function handleDelete(document) {
    if (!window.confirm(`Delete "${document.name}"?`)) return;
    setBusy(true);
    setError("");
    try {
      await deleteDocument(document.id);
      if (selected?.id === document.id) closeDrawer();
      await onDocumentsChanged();
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
      await onDocumentsChanged();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDetail(document) {
    setBusy(true);
    setError("");
    try {
      const detail = await getDocumentDetail(document.id);
      setSelected(detail);
      setChunks(null);
      setOpenChunkId(null);
      if (document.status === "ready") {
        setChunks(await getDocumentChunks(document.id));
      }
    } catch (detailError) {
      setError(detailError.message);
    } finally {
      setBusy(false);
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

  async function handleRescan() {
    setBusy(true);
    setError("");
    try {
      await onRescan();
      closeDrawer();
    } catch (rescanError) {
      setError(rescanError.message);
    } finally {
      setBusy(false);
    }
  }

  function closeDrawer() {
    setSelected(null);
    setChunks(null);
    setOpenChunkId(null);
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
          {user?.role === "admin" ? "PDF Management" : "Document Library"}
        </Typography>
        <Typography variant="body1" sx={{ mt: "18px", color: "#63706a" }}>
          {user?.role === "admin"
            ? "Manage uploaded documents, inspect metadata, and review retrieval chunks."
            : "Browse available documents, inspect metadata, and add relevant sources to your chat context."}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
        <Button variant="outlined" disabled={busy} onClick={onRefresh}>
          Refresh
        </Button>
        {user?.role === "admin" && (
          <Button variant="contained" disabled={busy} onClick={handleRescan}>
            {busy ? "Working..." : "Rescan files"}
          </Button>
        )}
      </Box>
      </Box>

      {user?.role === "admin" && <DocumentUpload compact onUploaded={onDocumentsChanged} />}

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
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search filename, title, region, policy area, keywords"
          size="small"
          sx={{ minWidth: 220, flex: 1 }}
        />
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            {STATUS_OPTIONS.map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}>
            <MenuItem value="all">All policy areas</MenuItem>
            {policyAreas.map((area) => (
              <MenuItem key={area} value={area}>{area}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)}>
            <MenuItem value="all">All regions</MenuItem>
            {regions.map((region) => (
              <MenuItem key={region} value={region}>{region}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <MenuItem value="all">All source types</MenuItem>
            {sourceTypes.map((sourceType) => (
              <MenuItem key={sourceType} value={sourceType}>{sourceType}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={filterSelectSx}>
          <Select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
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

        {loading ? (
          <Box sx={{ p: 2 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <Box
                key={i}
                sx={{
                  display: { xs: "block", md: "grid" },
                  gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 0.9fr) minmax(110px, 0.5fr) minmax(360px, auto)",
                  gap: 2,
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
                <Box sx={{ display: "flex", gap: 1, mt: { xs: 1, md: 0 }, justifySelf: "end" }}>
                  <Skeleton variant="rounded" width={110} height={40} />
                  <Skeleton variant="rounded" width={76} height={40} />
                  <Skeleton variant="rounded" width={88} height={40} />
                  <Skeleton variant="rounded" width={76} height={40} />
                </Box>
              </Box>
            ))}
          </Box>
        ) : filteredDocuments.length === 0 ? (
          <Typography sx={{ py: 4, textAlign: "center", color: "text.secondary" }}>
            No matching PDFs.
          </Typography>
        ) : (
          filteredDocuments.map((document) => (
            <Box
              key={document.id}
              sx={{
                display: { xs: "block", md: "grid" },
                gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 0.9fr) minmax(110px, 0.5fr) minmax(360px, auto)",
                gap: 2,
                px: 3,
                py: 2,
                borderBottom: "1px solid #eaece5",
                "&:last-child": { borderBottom: "none" },
                "&:hover": { bgcolor: "#fafaf7" },
              }}
            >
              {/* Document cell */}
              <Box sx={{ minWidth: 0 }}>
                <Typography component="strong" sx={{ fontWeight: 700, display: "block" }}>
                  {document.title || document.name}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.name}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {formatSize(document.size)} - {formatDate(document.uploaded_at)}
                </Typography>
              </Box>

              {/* Metadata cell */}
              <Box sx={{ minWidth: 0 }}>
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
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 800,
                    color:
                      document.status === "ready"
                        ? "success.main"
                        : document.status === "failed"
                          ? "error.main"
                          : "text.secondary",
                  }}
                >
                  {document.status || "unknown"}
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.page_count || 0} pages
                </Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  {document.chunk_count || 0} chunks
                </Typography>
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
                  justifyContent: { xs: "flex-start", md: "flex-end" },
                  justifySelf: { md: "end" },
                  mt: { xs: 2, md: 0 },
                  "& .MuiButton-root": {
                    minHeight: 40,
                  },
                }}
              >
                {contextSourceIds.includes(document.id) ? (
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={busy}
                    onClick={() => onRemoveSource(document.id)}
                    sx={{ color: "error.main", borderColor: "error.main" }}
                  >
                    Remove
                  </Button>
                ) : (
                  <Button
                    size="small"
                    variant="contained"
                    disabled={busy}
                    onClick={() => onAddSource(document.id)}
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

      <Menu anchorEl={moreMenuAnchor} open={Boolean(moreMenuAnchor)} onClose={closeMoreMenu}>
        <MenuItem onClick={() => runMoreAction(handleOpenSource)}>Open source</MenuItem>
        {user?.role === "admin" && <Divider />}
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

      <DocumentDrawer
        detail={selected}
        chunks={chunks}
        openChunkId={openChunkId}
        onToggleChunk={(chunkId) => setOpenChunkId(openChunkId === chunkId ? null : chunkId)}
        onClose={closeDrawer}
      />
    </Box>
  );
}
