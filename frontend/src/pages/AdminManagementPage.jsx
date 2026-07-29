import { useRef, useState } from "react";
import { Box, Card, Typography, Button, Chip } from "@mui/material";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import TaxonomySection from "./manage/TaxonomySection";
import LlmProvidersSection from "./manage/LlmProvidersSection";
import EmbeddingSection from "./manage/EmbeddingSection";
import RerankingSection from "./manage/RerankingSection";

const ACCENT = "#214f42";
const ORDER_KEY = "manage.sectionOrder"; // persists the admin's preferred order

// Sections shown in the Manage sidebar. Add more here as the admin area grows.
const SECTIONS = [
  {
    id: "taxonomy",
    label: "Document categories",
    desc: "Edit the two-level categories used to tag and filter documents. Changes apply to documents processed after saving; re-scan the library to re-tag existing files.",
    Component: TaxonomySection,
  },
  {
    id: "llm",
    label: "LLM & API keys",
    desc: "Configure LLM providers, API keys and the curated per-provider model lists used across Chat.",
    Component: LlmProvidersSection,
  },
  {
    id: "embedding",
    label: "Embedding model",
    desc: "Choose the embedding provider (local or API), import keys, and tune chunking, dimensions and retrieval thresholds.",
    Component: EmbeddingSection,
  },
  {
    id: "reranking",
    label: "Reranker",
    desc: "Choose the reranker (local cross-encoder or a /rerank API such as Zhipu), tune its evidence floor, or turn it off.",
    Component: RerankingSection,
  },
];

// Stored order, filtered to known sections and extended with any new ones.
function loadOrder() {
  const ids = SECTIONS.map((s) => s.id);
  try {
    const stored = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]");
    const valid = stored.filter((id) => ids.includes(id));
    return [...valid, ...ids.filter((id) => !valid.includes(id))];
  } catch {
    return ids;
  }
}

export default function AdminManagementPage({ user, onNavigate }) {
  const [order, setOrder] = useState(loadOrder);
  // Entering /manage shows the top (default) section.
  const [activeId, setActiveId] = useState(() => loadOrder()[0]);
  const dragId = useRef(null);

  if (user?.role !== "admin") {
    return (
      <Box component="section" sx={{ display: "flex", py: 4, textAlign: "center" }}>
        <Box sx={{ width: "100%", mt: 5 }}>
          <Typography sx={{ color: "text.secondary" }}>
            Access Denied. Administrator privileges required for management.
          </Typography>
          <Button variant="contained" onClick={() => onNavigate("auth")} sx={{ mt: 2 }}>
            Go to Login
          </Button>
        </Box>
      </Box>
    );
  }

  const ordered = order.map((id) => SECTIONS.find((s) => s.id === id)).filter(Boolean);
  const active = SECTIONS.find((s) => s.id === activeId) || ordered[0];
  const ActiveComponent = active.Component;

  function handleChildNavigate(target, options) {
    if (SECTIONS.some((section) => section.id === target)) {
      setActiveId(target);
      return;
    }
    onNavigate(target, options);
  }

  function persist(next) {
    try {
      localStorage.setItem(ORDER_KEY, JSON.stringify(next));
    } catch {
      /* ignore storage errors */
    }
  }

  // Live reorder as the dragged item passes over another; persisted on drop.
  function handleDragEnter(overId) {
    const dragging = dragId.current;
    if (!dragging || dragging === overId) return;
    setOrder((prev) => {
      const from = prev.indexOf(dragging);
      const to = prev.indexOf(overId);
      if (from < 0 || to < 0) return prev;
      const next = [...prev];
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  }

  function handleDragEnd() {
    dragId.current = null;
    setOrder((prev) => {
      persist(prev);
      return prev;
    });
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
      {/* Sidebar: draggable section navigation */}
      <Card sx={{ width: { xs: "100%", md: 288 }, flexShrink: 0, p: 3, alignSelf: "flex-start" }}>
        <Typography variant="subtitle2">Management</Typography>
        <Typography variant="h2" sx={{ fontSize: 24, mb: 0.5 }}>Site configuration</Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2 }}>
          Drag to reorder. The top item is the default view when you open Manage.
        </Typography>

        <Box sx={{ display: "grid", gap: 0.75, mb: 2 }}>
          {ordered.map((section, index) => {
            const selected = section.id === activeId;
            const isDefault = index === 0;
            return (
              <Box
                key={section.id}
                draggable
                onDragStart={() => {
                  dragId.current = section.id;
                }}
                onDragEnter={() => handleDragEnter(section.id)}
                onDragOver={(event) => event.preventDefault()}
                onDragEnd={handleDragEnd}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0.25,
                  borderRadius: "8px",
                  cursor: "grab",
                  "&:active": { cursor: "grabbing" },
                }}
              >
                <DragIndicatorIcon
                  sx={{ fontSize: 18, color: selected ? "rgba(255,255,255,0.7)" : "#b6bdb5" }}
                />
                <Button
                  onClick={() => setActiveId(section.id)}
                  sx={{
                    flex: 1,
                    minWidth: 0,
                    gap: 0.75,
                    px: 1.25,
                    justifyContent: "flex-start",
                    borderRadius: "8px",
                    fontWeight: 750,
                    fontSize: 13.5,
                    textTransform: "none",
                    color: selected ? "#fff" : "#2f3a34",
                    backgroundColor: selected ? ACCENT : "transparent",
                    "&:hover": { backgroundColor: selected ? "#1a3f35" : "#eef2ee" },
                  }}
                >
                  <Box
                    component="span"
                    sx={{
                      flex: 1,
                      textAlign: "left",
                      minWidth: 0,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {section.label}
                  </Box>
                  {isDefault && (
                    <Chip
                      label="Default"
                      size="small"
                      sx={{
                        flexShrink: 0,
                        height: 18,
                        fontSize: 10,
                        fontWeight: 700,
                        "& .MuiChip-label": { px: 0.75 },
                        color: selected ? "#fff" : ACCENT,
                        backgroundColor: selected ? "rgba(255,255,255,0.2)" : "#dfe8e0",
                      }}
                    />
                  )}
                </Button>
              </Box>
            );
          })}
        </Box>

        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          {active.desc}
        </Typography>
      </Card>

      {/* Main content: active section */}
      <Card sx={{ flex: 1, p: 3 }}>
        <ActiveComponent user={user} onNavigate={handleChildNavigate} />
      </Card>
    </Box>
  );
}
