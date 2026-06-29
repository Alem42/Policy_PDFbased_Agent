import { useId } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

export default function CitationList({ citations = [], onOpenSource }) {
  const citationListId = useId();
  const availableCitations = citations.filter(
    (citation) =>
      citation &&
      (citation.document_id || citation.title || citation.quote || citation.page != null),
  );

  if (availableCitations.length === 0) return null;

  return (
    <Box
      component="section"
      aria-label="Evidence sources"
      sx={{
        mt: 2,
        pt: 2,
        borderTop: "1px solid #e2e5df",
      }}
    >
      <Typography variant="subtitle2">Evidence</Typography>
      <Typography variant="body2" sx={{ mt: 0.5, mb: 1.5, color: "text.secondary" }}>
        Review the retrieved passages that support this response.
      </Typography>

      <Stack spacing={1}>
        {availableCitations.map((citation, index) => {
          const title = citation.title || "Untitled source";
          const pageLabel = citation.page != null ? `Page ${citation.page}` : "Page unavailable";
          const citationKey =
            citation.chunk_id || `${citation.document_id || title}-${citation.page || 0}-${index}`;
          const contentId = `${citationListId}-citation-${index}-content`;
          const headerId = `${citationListId}-citation-${index}-header`;

          return (
            <Accordion
              key={citationKey}
              disableGutters
              elevation={0}
              sx={{
                border: "1px solid #dfe4de",
                borderRadius: "8px !important",
                overflow: "hidden",
                "&::before": { display: "none" },
              }}
            >
              <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                aria-controls={contentId}
                id={headerId}
                sx={{
                  px: 1.5,
                  minHeight: 54,
                  "& .MuiAccordionSummary-content": {
                    alignItems: "center",
                    gap: 1,
                    minWidth: 0,
                  },
                }}
              >
                <Chip label={`Source ${index + 1}`} size="small" color="primary" />
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 800 }}>
                    {title}
                  </Typography>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    {pageLabel}
                  </Typography>
                </Box>
              </AccordionSummary>

              <AccordionDetails
                id={contentId}
                aria-labelledby={headerId}
                sx={{ px: 1.5, pt: 0 }}
              >
                {citation.quote ? (
                  <Box
                    component="blockquote"
                    sx={{
                      m: 0,
                      mb: 1.5,
                      px: 1.5,
                      py: 1,
                      borderLeft: "3px solid",
                      borderColor: "primary.main",
                      bgcolor: "#f5f7f3",
                      color: "text.secondary",
                    }}
                  >
                    <Typography variant="body2">{citation.quote}</Typography>
                  </Box>
                ) : (
                  <Typography variant="body2" sx={{ mb: 1.5, color: "text.secondary" }}>
                    No supporting excerpt is available for this source.
                  </Typography>
                )}

                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<OpenInNewIcon />}
                  disabled={!citation.document_id || !onOpenSource}
                  onClick={() => onOpenSource(citation)}
                  aria-label={`Open ${title} PDF at ${pageLabel.toLowerCase()}`}
                >
                  Open source PDF
                </Button>
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Stack>
    </Box>
  );
}
