import { Box, Typography, Button, Card, CardContent, Grid, Skeleton } from "@mui/material";
import DocumentUpload from "../components/DocumentUpload";
import { formatDate, formatSize } from "../utils/format";

export default function AdminDashboard({
  documents,
  loading,
  user,
  onDocumentsChanged,
  onNavigate,
}) {
  if (!(user.role === "admin")) {
    return (
      <Box component="section" sx={{ py: 4, textAlign: "center" }}>
        <Typography sx={{ py: 4, color: "text.secondary" }}>
          Access Denied. Administrator privileges required.
        </Typography>
        <Button variant="contained" onClick={() => onNavigate("auth")}>
          Go to Login
        </Button>
      </Box>
    );
  }

  const readyCount = documents.filter((document) => document.status === "ready").length;
  const chunkCount = documents.reduce((total, document) => total + (document.chunk_count || 0), 0);

  return (
    <Box component="section">
      {/* Hero */}
      <Box sx={{ maxWidth: 860, pt: "54px", pb: "28px" }}>
        <Typography variant="subtitle2" sx={{ mb: "10px" }}>Admin Workspace</Typography>
        <Typography variant="h1">Knowledge Base Management</Typography>
        <Typography variant="body1" sx={{ mt: "18px", color: "#63706a" }}>
          Manage policy documents, upload new PDFs, and monitor indexing status.
        </Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 3 }}>
          <Button variant="outlined" onClick={() => onNavigate("chat")}>
            ← Back to Q&A
          </Button>
        </Box>
      </Box>

      {/* Stats */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent sx={{ p: "18px", "&:last-child": { pb: "18px" } }}>
              <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                Total documents
              </Typography>
              <Typography variant="h3" sx={{ mt: 1, fontSize: 34 }}>
                {documents.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent sx={{ p: "18px", "&:last-child": { pb: "18px" } }}>
              <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                Ready for Q&A
              </Typography>
              <Typography variant="h3" sx={{ mt: 1, fontSize: 34 }}>
                {readyCount}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent sx={{ p: "18px", "&:last-child": { pb: "18px" } }}>
              <Typography variant="body2" sx={{ color: "#64716b", fontWeight: 800 }}>
                Indexed chunks
              </Typography>
              <Typography variant="h3" sx={{ mt: 1, fontSize: 34 }}>
                {chunkCount}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* All Documents */}
      <Card sx={{ p: 3 }}>
        <Box sx={{ mb: "20px" }}>
          <Typography variant="subtitle2">Library</Typography>
          <Typography variant="h2">All Documents</Typography>
        </Box>

        <DocumentUpload onUploaded={onDocumentsChanged} />

        <Box sx={{ display: "grid", gap: "10px" }}>
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <Box
                key={i}
                sx={{
                  display: "grid",
                  gridTemplateColumns: "46px minmax(0, 1fr)",
                  gap: "12px",
                  alignItems: "center",
                  p: "13px",
                  border: "1px solid #e2e5df",
                  borderRadius: "8px",
                  bgcolor: "#fff",
                }}
              >
                <Skeleton variant="rounded" width={42} height={48} sx={{ borderRadius: "7px" }} />
                <Box>
                  <Skeleton variant="text" width="60%" height={20} />
                  <Skeleton variant="text" width="80%" height={16} />
                  <Skeleton variant="text" width="40%" height={16} />
                </Box>
              </Box>
            ))
          ) : documents.length === 0 ? (
            <Typography sx={{ py: 4, textAlign: "center", color: "text.secondary" }}>
              No PDFs uploaded yet.
            </Typography>
          ) : (
            documents.map((document) => (
              <Box
                key={document.id || document.name}
                sx={{
                  display: "grid",
                  gridTemplateColumns: "46px minmax(0, 1fr)",
                  gap: "12px",
                  alignItems: "center",
                  p: "13px",
                  border: "1px solid #e2e5df",
                  borderRadius: "8px",
                  bgcolor: "#fff",
                }}
              >
                <Box
                  sx={{
                    display: "grid",
                    width: 42,
                    height: 48,
                    placeItems: "center",
                    borderRadius: "7px",
                    color: "#a54a42",
                    bgcolor: "#f8e9e5",
                    fontSize: 11,
                    fontWeight: 900,
                  }}
                >
                  PDF
                </Box>
                <Box sx={{ minWidth: 0 }}>
                  <Typography component="strong" sx={{ fontWeight: 700 }}>
                    {document.title || document.name}
                  </Typography>
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    {document.name}
                  </Typography>
                  <Typography variant="body2" sx={{ color: "text.secondary" }}>
                    {formatSize(document.size)} - {document.status || "ready"} -{" "}
                    {formatDate(document.uploaded_at)}
                  </Typography>
                </Box>
              </Box>
            ))
          )}
        </Box>
      </Card>
    </Box>
  );
}