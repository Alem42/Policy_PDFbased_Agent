import { useEffect, useState } from "react";
import {
  Box,
  Card,
  Typography,
  Button,
  TextField,
  Alert,
  Skeleton,
  IconButton,
  Chip,
  Divider,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/Delete";
import { getTaxonomy, saveTaxonomy } from "../api";

const ACCENT = "#214f42";

// Deep-clone the tree so edits never mutate the loaded copy.
function cloneGroups(groups) {
  return groups.map((g) => ({
    parent: g.parent || "",
    source_ref: g.source_ref || "",
    children: [...(g.children || [])],
  }));
}

export default function AdminManagementPage({ user, onNavigate }) {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [childDrafts, setChildDrafts] = useState({}); // parentIndex -> in-progress child text

  async function load() {
    setLoading(true);
    setError("");
    try {
      const result = await getTaxonomy();
      setGroups(cloneGroups(result.groups || []));
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user?.role === "admin") load();
    else setLoading(false);
  }, [user]);

  function updateParent(index, field, value) {
    setGroups((prev) => prev.map((g, i) => (i === index ? { ...g, [field]: value } : g)));
  }

  function addParent() {
    setGroups((prev) => [...prev, { parent: "", source_ref: "", children: [] }]);
  }

  function removeParent(index) {
    setGroups((prev) => prev.filter((_, i) => i !== index));
  }

  function addChild(index) {
    const draft = (childDrafts[index] || "").trim();
    if (!draft) return;
    setGroups((prev) =>
      prev.map((g, i) =>
        i === index && !g.children.includes(draft)
          ? { ...g, children: [...g.children, draft] }
          : g,
      ),
    );
    setChildDrafts((prev) => ({ ...prev, [index]: "" }));
  }

  function removeChild(index, child) {
    setGroups((prev) =>
      prev.map((g, i) =>
        i === index ? { ...g, children: g.children.filter((c) => c !== child) } : g,
      ),
    );
  }

  async function handleSave() {
    // Clean + validate: trim, drop blanks, require a parent name and >=1 child each.
    const cleaned = groups
      .map((g) => ({
        parent: g.parent.trim(),
        source_ref: g.source_ref.trim() || null,
        children: [...new Set(g.children.map((c) => c.trim()).filter(Boolean))],
      }))
      .filter((g) => g.parent);

    if (cleaned.length === 0) {
      setError("Add at least one parent category.");
      return;
    }
    const emptyParent = cleaned.find((g) => g.children.length === 0);
    if (emptyParent) {
      setError(`"${emptyParent.parent}" needs at least one subcategory.`);
      return;
    }

    setBusy(true);
    setNotice("");
    setError("");
    try {
      const result = await saveTaxonomy(cleaned);
      setGroups(cloneGroups(result.groups || []));
      setNotice("Taxonomy saved. New wording applies to documents processed from now on.");
    } catch (saveError) {
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  }

  if (user?.role !== "admin") {
    return (
      <Box component="section" sx={{ display: "flex", py: 4, textAlign: "center" }}>
        <Box sx={{ width: "100%", mt: 5 }}>
          <Typography sx={{ color: "text.secondary" }}>
            Access Denied. Administrator privileges required for global management.
          </Typography>
          <Button variant="contained" onClick={() => onNavigate("auth")} sx={{ mt: 2 }}>
            Go to Login
          </Button>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      component="section"
      sx={{
        display: "flex",
        gap: 3,
        flexDirection: { xs: "column", md: "row" },
        pt: "54px",
        pb: "28px",
      }}
    >
      {/* Sidebar */}
      <Card sx={{ width: { xs: "100%", md: 260 }, flexShrink: 0, p: 3, alignSelf: "flex-start" }}>
        <Typography variant="subtitle2">Global Management</Typography>
        <Typography variant="h2" sx={{ fontSize: 24, mb: 2 }}>Site content</Typography>
        <Button
          fullWidth
          sx={{
            justifyContent: "flex-start",
            color: "#fff",
            backgroundColor: ACCENT,
            borderRadius: "8px",
            fontWeight: 750,
            textTransform: "none",
            mb: 2,
            "&:hover": { backgroundColor: "#1a3f35" },
          }}
        >
          Policy taxonomy
        </Button>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Edit the two-level categories used to tag and filter documents. Changes apply to
          documents processed after saving; re-scan the library to re-tag existing files.
        </Typography>
      </Card>

      {/* Main content */}
      <Card sx={{ flex: 1, p: 3 }}>
        <Box sx={{ mb: "20px" }}>
          <Typography variant="subtitle2">Configuration</Typography>
          <Typography variant="h2" sx={{ fontSize: 24 }}>Policy taxonomy</Typography>
        </Box>

        {loading ? (
          <Box sx={{ py: 2 }}>
            <Skeleton variant="rounded" height={120} sx={{ mb: 2 }} />
            <Skeleton variant="rounded" height={120} sx={{ mb: 2 }} />
          </Box>
        ) : (
          <>
            {notice && <Alert severity="success" sx={{ mb: 2 }}>{notice}</Alert>}
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <Box sx={{ display: "grid", gap: 2 }}>
              {groups.map((group, index) => (
                <Box
                  key={index}
                  sx={{ p: 2, border: "1px solid #e2e5df", borderRadius: 2, display: "grid", gap: 1.5 }}
                >
                  <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                    <TextField
                      value={group.parent}
                      onChange={(e) => updateParent(index, "parent", e.target.value)}
                      placeholder="Parent category (e.g. Health Policy)"
                      size="small"
                      sx={{ flex: 1 }}
                    />
                    <TextField
                      value={group.source_ref}
                      onChange={(e) => updateParent(index, "source_ref", e.target.value)}
                      placeholder="Source (e.g. OECD.AI)"
                      size="small"
                      sx={{ width: 180 }}
                    />
                    <IconButton
                      size="small"
                      onClick={() => removeParent(index)}
                      sx={{ color: "#b23b3b" }}
                      aria-label="Remove parent category"
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Box>

                  {/* Subcategory chips */}
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                    {group.children.length === 0 && (
                      <Typography variant="caption" sx={{ color: "text.secondary" }}>
                        No subcategories yet.
                      </Typography>
                    )}
                    {group.children.map((child) => (
                      <Chip
                        key={child}
                        label={child}
                        onDelete={() => removeChild(index, child)}
                        size="small"
                        sx={{ backgroundColor: "#eef2ee", fontWeight: 600 }}
                      />
                    ))}
                  </Box>

                  {/* Add subcategory */}
                  <Box sx={{ display: "flex", gap: 1 }}>
                    <TextField
                      value={childDrafts[index] || ""}
                      onChange={(e) => setChildDrafts((p) => ({ ...p, [index]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addChild(index);
                        }
                      }}
                      placeholder="Add subcategory and press Enter"
                      size="small"
                      sx={{ flex: 1, maxWidth: 360 }}
                    />
                    <Button size="small" startIcon={<AddIcon />} onClick={() => addChild(index)}>
                      Add
                    </Button>
                  </Box>
                </Box>
              ))}
            </Box>

            <Divider sx={{ my: 2 }} />

            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
              <Button variant="outlined" startIcon={<AddIcon />} onClick={addParent}>
                Add parent category
              </Button>
              <Box sx={{ flex: 1 }} />
              <Button variant="outlined" disabled={busy} onClick={load}>
                Reload
              </Button>
              <Button variant="contained" disabled={busy} onClick={handleSave}>
                {busy ? "Saving..." : "Save taxonomy"}
              </Button>
            </Box>
          </>
        )}
      </Card>
    </Box>
  );
}
