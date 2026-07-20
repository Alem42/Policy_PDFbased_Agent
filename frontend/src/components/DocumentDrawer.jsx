import { useRef } from "react";
import {
  Box,
  Typography,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Drawer,
  Skeleton,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

const METADATA_FIELDS = [
  { key: "name", label: "Filename" },
  { key: "country_region", label: "Region", fallback: "Unknown" },
  { key: "year", label: "Year", fallback: "Unknown" },
  { key: "source_type", label: "Source type", fallback: "Unknown" },
  { key: "source_organisation", label: "Source organisation", fallback: "Unknown" },
  { key: "language", label: "Language", fallback: "Unknown" },
  { key: "publication_date", label: "Publication date", fallback: "Unknown" },
];

export default function DocumentDrawer({
  detail,
  detailLoading,
  chunks,
  chunksLoading,
  openChunkId,
  onToggleChunk,
  onClose,
}) {
  const lastDetailRef = useRef(detail);
  const lastChunksRef = useRef(chunks);

  if (detail) {
    lastDetailRef.current = detail;
    lastChunksRef.current = chunks;
  }
  const isOpen = !!detail || !!detailLoading;
  // While a new detail fetch is in flight, don't fall back to the previous
  // document's cached data -- that would mislabel it as the new one.
  const renderedDetail = detail || (detailLoading ? null : lastDetailRef.current);
  const renderedChunks = detail ? chunks : (isOpen ? null : lastChunksRef.current);
  const renderedChunksLoading = detail ? chunksLoading : false;

  return (
    <Drawer
      anchor="right"
      open={isOpen}
      onClose={onClose}
      transitionDuration={{ enter: 280, exit: 220 }}
      slotProps={{
        paper: {
          sx: {
            width: { xs: "calc(100vw - 24px)", sm: 480, md: 520 },
            maxWidth: 520,
            overflowX: "hidden",
            overflowY: "auto",
            borderRadius: 0,
            boxShadow: "-18px 0 50px rgba(31, 39, 35, 0.18)",
          },
        },
      }}
    >
      {!renderedDetail && detailLoading && (
        <Box sx={{ p: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
            <Box sx={{ width: "70%" }}>
              <Skeleton variant="text" width="40%" height={20} />
              <Skeleton variant="text" width="85%" height={36} />
            </Box>
            <IconButton onClick={onClose} aria-label="Close details" size="small">
              <CloseIcon />
            </IconButton>
          </Box>
          <Box sx={{ display: "grid", gap: 2, mb: 3 }}>
            {Array.from({ length: 5 }).map((_, index) => (
              <Box key={index}>
                <Skeleton variant="text" width="30%" height={16} />
                <Skeleton variant="text" width="55%" height={22} />
              </Box>
            ))}
          </Box>
          <Skeleton variant="rounded" height={80} sx={{ borderRadius: 2 }} />
        </Box>
      )}

      {renderedDetail && (
        <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          mb: 3,
        }}
      >
        <Box>
          <Typography variant="subtitle2">
            {renderedChunks ? "Document chunks" : "Document record"}
          </Typography>
          <Typography variant="h2">{renderedDetail.title || renderedDetail.name}</Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="Close details" size="small">
          <CloseIcon />
        </IconButton>
      </Box>

      {/* Metadata list */}
      <Box component="dl" sx={{ display: "grid", gap: 2, mb: 3 }}>
        {METADATA_FIELDS.map(({ key, label, fallback }) => (
          <Box key={key} sx={{ m: 0 }}>
            <Typography
              component="dt"
              variant="body2"
              sx={{ fontWeight: 800, color: "#64716b", mb: 0.25 }}
            >
              {label}
            </Typography>
            <Typography component="dd" sx={{ m: 0 }}>
              {renderedDetail[key] || fallback}
            </Typography>
          </Box>
        ))}
        <Box>
          <Typography
            component="dt"
            variant="body2"
            sx={{ fontWeight: 800, color: "#64716b", mb: 0.25 }}
          >
            Access
          </Typography>
          <Typography component="dd" sx={{ m: 0 }}>
            {renderedDetail.approved ? "Approved" : "Not approved"} / {renderedDetail.access_level || "public"}
          </Typography>
        </Box>
        <Box>
          <Typography
            component="dt"
            variant="body2"
            sx={{ fontWeight: 800, color: "#64716b", mb: 0.25 }}
          >
            Policy areas
          </Typography>
          <Typography component="dd" sx={{ m: 0 }}>
            {(renderedDetail.policy_areas || []).length > 0
              ? (renderedDetail.policy_areas || []).map((area) => (
                  <Chip key={area} label={area} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
                ))
              : "None"}
          </Typography>
        </Box>
        <Box>
          <Typography
            component="dt"
            variant="body2"
            sx={{ fontWeight: 800, color: "#64716b", mb: 0.25 }}
          >
            Keywords
          </Typography>
          <Typography component="dd" sx={{ m: 0 }}>
            {(renderedDetail.keywords || []).length > 0
              ? (renderedDetail.keywords || []).map((kw) => (
                  <Chip key={kw} label={kw} size="small" variant="outlined" sx={{ mr: 0.5, mb: 0.5 }} />
                ))
              : "None"}
          </Typography>
        </Box>
      </Box>

      {/* Summary */}
      {renderedDetail.summary && (
        <Typography
          variant="body2"
          sx={{ color: "#63706a", lineHeight: 1.6, mb: 2, p: 2, bgcolor: "#f9faf7", borderRadius: 2 }}
        >
          {renderedDetail.summary}
        </Typography>
      )}

      {/* Metadata JSON */}
      <Accordion sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 800 }}>Metadata JSON</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box
            component="pre"
            sx={{
              fontSize: 12,
              bgcolor: "#f5f5f0",
              p: 2,
              borderRadius: 1,
              overflow: "auto",
              maxHeight: 300,
            }}
          >
            {JSON.stringify(renderedDetail.metadata_json || {}, null, 2)}
          </Box>
        </AccordionDetails>
      </Accordion>

      {/* Chunks */}
      {(renderedChunks || renderedChunksLoading) && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Chunks</Typography>
          {renderedChunksLoading && !renderedChunks
            ? Array.from({ length: 4 }).map((_, index) => (
                <Skeleton
                  key={index}
                  variant="rounded"
                  height={44}
                  sx={{ mb: 1, borderRadius: 2 }}
                />
              ))
            : renderedChunks.chunks.map((chunk) => (
            <Accordion
              key={chunk.id}
              expanded={openChunkId === chunk.id}
              onChange={() => onToggleChunk(chunk.id)}
              disableGutters
              sx={{
                border: "1px solid #e2e5df",
                borderRadius: 2,
                mb: 1,
                overflow: "hidden",
                boxShadow: "none",
                "&::before": { display: "none" },
                "&.Mui-expanded": { my: 1 },
              }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                  Chunk {chunk.chunk_index} - pages {chunk.page_start}
                  {chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""} -{" "}
                  {chunk.token_count} tokens
                  {chunk.language ? ` - ${chunk.language}` : ""}
                </Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ p: 2, bgcolor: "#f9faf7" }}>
                <Box
                  component="pre"
                  sx={{
                    fontSize: 12,
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    mb: 2,
                  }}
                >
                  {chunk.text}
                </Box>
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="body2">Chunk metadata</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box
                      component="pre"
                      sx={{ fontSize: 12, whiteSpace: "pre-wrap" }}
                    >
                      {JSON.stringify(
                        {
                          id: chunk.id,
                          embedding_model: chunk.embedding_model,
                          metadata_json: chunk.metadata_json,
                          keywords: chunk.keywords,
                        },
                        null,
                        2,
                      )}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      )}
        </Box>
      )}
    </Drawer>
  );
}
