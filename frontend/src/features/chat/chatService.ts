import { apiRequest } from "../../lib/api";
import { ChatRequest, ChatResponse } from "../../lib/types";

export function askPolicyQuestion(payload: ChatRequest) {
  return apiRequest<ChatResponse>("/chat", {
    method: "POST",
    body: payload
  });
}
