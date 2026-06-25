export const storyGroups = {
  documents: [
    "W11CBREAD-36: As a policy researcher, I want to search the policy files by filename or keywords, so that I can quickly and accurately locate specific document(s).",
    "W11CBREAD-16: As a policy researcher, I want to open a document detail page with metadata, summary, source information, and available snippets, so that I can decide whether the document is relevant before asking the AI.",
    "W11CBREAD-14: As a user, I want to browse and filter policy documents by policy area, country, year, source, and tags, so that I can discover relevant cases before asking questions.",
    "W11CBREAD-10: As a policy researcher, I want to select one or more documents as the scope of my question, so that the AI response is focused on relevant sources."
  ],
  chat: [
    "W11CBREAD-27: As a policy student, I want the system to provide guided follow-up questions after an AI answer, so that I can continue learning about related policy issues, implementation challenges, and real-world examples.",
    "W11CBREAD-26: As a policy student, I want the AI to explain policy cases in clear, beginner-friendly language, so that I can understand complex policy concepts without needing extensive prior knowledge.",
    "W11CBREAD-25: As a policy researcher, I want to export or save an AI-generated answer together with its citations and selected source documents, so that I can reuse the result in reports, presentations, or further policy research.",
    "W11CBREAD-24: As a policy researcher, I want the AI response to be structured into relevant cases, key lessons, risks, implementation considerations, and practical recommendations, so that I can quickly turn policy documents into actionable insights.",
    "W11CBREAD-20: As a policy researcher, I want to rate whether an AI answer is helpful and whether its citations are useful, so that the system can improve retrieval and answer quality over time.",
    "W11CBREAD-19: As a policy researcher, I want to click citations in an AI response and view the supporting source snippet, so that I can verify the evidence without leaving the answer page.",
    "W11CBREAD-18: As a policy researcher, I want to see clear loading, retrieval, and answer generation states, so that I understand what the system is doing while waiting for an AI response.",
    "W11CBREAD-13: As a user, I want the system to tell me when there is insufficient evidence in the current document library, so that I do not mistake unsupported AI output for fact.",
    "W11CBREAD-11: As a policy researcher, I want the AI response to include citations and source snippets, so that I can verify the evidence behind the answer.",
    "W11CBREAD-9: As a policy researcher, I want to ask natural-language questions about selected policy documents, so that I can quickly obtain evidence-based policy insights."
  ],
  learning: [
    "W11CBREAD-35: As a policy student, I want the system to provide a comparison between two selected policy cases in terms of context, policy approach, outcomes, and lessons learned, so that I can learn how different policy decisions lead to different results.",
    "W11CBREAD-34: As a policy student, I want the system to generate a short learning summary of a selected policy document, including key concepts, main arguments, and important policy terms, so that I can understand the document before reading it in full.",
    "W11CBREAD-15: As a policy researcher, I want to compare policy cases across different countries or regions, so that I can understand differences in policy design and outcomes."
  ],
  admin: [
    "W11CBREAD-12: As a system admin, I want to view document processing progress, including upload, parsing, segmentation, embedding, and indexing status, so that I know whether a document is ready for retrieval.",
    "W11CBREAD-8: As a system admin, I want to log in securely by entering my username and password, and the system to block all unauthorised users, so that the system database is secured from tampering by malicious users and spam.",
    "W11CBREAD-7: As a system admin, I want to upload complex policy PDF files and have the system automatically perform semantic segmentation, so that when a policy researcher asks the AI, it can retrieve the full unbroken context and provide an accurate response.",
    "W11CBREAD-5: As a system admin, I want to be able to delete specific policy file, so that completely erasing the document from search index and preventing policy researchers and the AI from continuing to reference incorrect or outdated contents.",
    "W11CBREAD-4: As a system admin, I want to search the policy files by file id, filename or keywords, so that I can quickly and accurately locate specific document(s).",
    "W11CBREAD-3: As a system admin, I want to be able to browse and filter all files added to the database, so that I can have an overview of files and ensure files have been successfully processed into their respective subcategories.",
    "W11CBREAD-2: As a system admin, I want the system to automatically recognise the meta tags for a file after it has been uploaded, and allow me to maunally select or edit these tags, so that later on policy researchers can filter files precisely based on these tags.",
    "W11CBREAD-1: As a system admin, I want to be able to upload multiple policy PDF files, so that I can efficiently expand the policy database"
  ],
  crawler: [
    "W11CBREAD-23: As an admin, I want to monitor website crawling status, so that I know whether new documents have been successfully added to the knowledge base.",
    "W11CBREAD-22: As an admin, I want to register trusted official websites, so that the system can collect policy documents from approved sources."
  ],
  savedAnswers: [
    "W11CBREAD-25: As a policy researcher, I want to export or save an AI-generated answer together with its citations and selected source documents, so that I can reuse the result in reports, presentations, or further policy research."
  ],
  adminLogin: [
    "W11CBREAD-8: As a system admin, I want to log in securely by entering my username and password, and the system to block all unauthorised users, so that the system database is secured from tampering by malicious users and spam."
  ],
  adminDocuments: [
    "W11CBREAD-5: As a system admin, I want to be able to delete specific policy file, so that completely erasing the document from search index and preventing policy researchers and the AI from continuing to reference incorrect or outdated contents.",
    "W11CBREAD-4: As a system admin, I want to search the policy files by file id, filename or keywords, so that I can quickly and accurately locate specific document(s).",
    "W11CBREAD-3: As a system admin, I want to be able to browse and filter all files added to the database, so that I can have an overview of files and ensure files have been successfully processed into their respective subcategories.",
    "W11CBREAD-2: As a system admin, I want the system to automatically recognise the meta tags for a file after it has been uploaded, and allow me to maunally select or edit these tags, so that later on policy researchers can filter files precisely based on these tags."
  ],
  adminUpload: [
    "W11CBREAD-7: As a system admin, I want to upload complex policy PDF files and have the system automatically perform semantic segmentation, so that when a policy researcher asks the AI, it can retrieve the full unbroken context and provide an accurate response.",
    "W11CBREAD-1: As a system admin, I want to be able to upload multiple policy PDF files, so that I can efficiently expand the policy database"
  ],
  processing: [
    "W11CBREAD-12: As a system admin, I want to view document processing progress, including upload, parsing, segmentation, embedding, and indexing status, so that I know whether a document is ready for retrieval."
  ]
} as const;
