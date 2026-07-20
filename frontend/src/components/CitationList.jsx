import { useState } from "react";
import {
  Box,
  Button,
  Chip,
  Collapse,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

export default function CitationList({ citations = [], onOpenSource, lowEvidence = false }) {
  const [expanded, setExpanded] = useState(false);

  const available = citations.filter(
    (c) => c && (c.document_id || c.title || c.quote || c.page != null),
  );
  if (available.length === 0) return null;

  const preview = available.slice(0, 3);
  const rest = available.slice(3);

  const accentColor = lowEvidence ? "#d84315" : "#214f42";
  const borderColor = lowEvidence ? "#ffccbc" : "#e2e5df";

  return (
    <Box sx={{ mt: 2, pt: 2, borderTop: `1px solid ${borderColor}` }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Typography
          variant="subtitle2"
          sx={{
            fontSize: 12,
            color: lowEvidence ? "#bf360c" : "text.secondary",
            textTransform: "uppercase",
            letterSpacing: 0.5,
          }}
        >
          {lowEvidence ? "⚠ Low-confidence sources" : "Evidence"} · {available.length} source{available.length !== 1 ? "s" : ""}
        </Typography>
        {rest.length > 0 && (
          <Button
            size="small"
            variant="text"
            endIcon={expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
            onClick={() => setExpanded((v) => !v)}
            sx={{ fontSize: "0.7em", color: accentColor, textTransform: "none", py: 0, minWidth: 0 }}
          >
            {expanded ? "Show less" : `+${rest.length} more`}
          </Button>
        )}
      </Box>

      {[...preview, ...(expanded ? rest : [])].map((citation, index) => (
        <CitationCard
          key={citation.chunk_id || `${citation.document_id}-${index}`}
          citation={citation}
          index={index}
          onOpenSource={onOpenSource}
          lowEvidence={lowEvidence}
        />
      ))}
    </Box>
  );
}

function CitationCard({ citation, index, onOpenSource, lowEvidence = false }) {
  const [open, setOpen] = useState(lowEvidence);
  const title = citation.title || "Untitled source";
  const hasQuote = Boolean(citation.quote);
  const accentColor = lowEvidence ? "#d84315" : "#214f42";
  const chipBg = lowEvidence ? "#d84315" : "#214f42";
  const quoteBorder = lowEvidence ? "#ff8a65" : "#214f42";
  const quoteBg = lowEvidence ? "#fff8f5" : "#f0f5f2";

  return (
    <Box
      sx={{
        mb: 1,
        border: "1px solid",
        borderColor: lowEvidence ? "#ffccbc" : "#dfe4de",
        borderRadius: 2,
        overflow: "hidden",
        bgcolor: lowEvidence ? "#fff9f7" : "#fafaf8",
      }}
    >
      {/* Header row */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 1,
          cursor: hasQuote ? "pointer" : "default",
          "&:hover": hasQuote ? { bgcolor: lowEvidence ? "#fff0eb" : "#f3f5f1" } : {},
        }}
        onClick={() => hasQuote && setOpen((v) => !v)}
      >
        <Chip
          label={`[${index + 1}]`}
          size="small"
          sx={{
            bgcolor: chipBg,
            color: "#fff",
            fontWeight: 700,
            fontSize: "0.7em",
            height: 20,
            flexShrink: 0,
            "& .MuiChip-label": { px: 0.75 },
          }}
        />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: 600,
              fontSize: 13,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {title}
          </Typography>
          {citation.page != null && (
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: 11 }}>
              Page {citation.page}
            </Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
          {citation.document_id && onOpenSource && (
            <Button
              size="small"
              variant="text"
              startIcon={<OpenInNewIcon sx={{ fontSize: "12px !important" }} />}
              onClick={(e) => { e.stopPropagation(); onOpenSource(citation); }}
              sx={{ fontSize: "0.7em", color: accentColor, textTransform: "none", py: 0, px: 0.75, minWidth: 0 }}
            >
              Open
            </Button>
          )}
          {hasQuote && (
            open
              ? <ExpandLessIcon sx={{ fontSize: 16, color: "text.secondary" }} />
              : <ExpandMoreIcon sx={{ fontSize: 16, color: "text.secondary" }} />
          )}
        </Box>
      </Box>

      {/* Quote */}
      {hasQuote && (
        <Collapse in={open}>
          <Box
            sx={{
              mx: 1.5,
              mb: 1.5,
              px: 1.5,
              py: 1,
              borderLeft: `3px solid ${quoteBorder}`,
              bgcolor: quoteBg,
              borderRadius: "0 4px 4px 0",
            }}
          >
            <Typography
              variant="body2"
              sx={{
                color: lowEvidence ? "#5d2b1e" : "#4a5a54",
                fontSize: 13,
                lineHeight: 1.65,
                fontStyle: "italic",
                wordBreak: "break-word",
              }}
            >
              &ldquo;{citation.quote.length > 320 ? citation.quote.slice(0, 320) + "…" : citation.quote}&rdquo;
            </Typography>
          </Box>
        </Collapse>
      )}
    </Box>
  );
}
