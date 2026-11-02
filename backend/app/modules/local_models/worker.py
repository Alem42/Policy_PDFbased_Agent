"""Qwen inference follows the official model cards; no application/database imports."""

from __future__ import annotations


def worker_main(connection, cache_dir: str):
    models = {}
    try:
        import torch
        from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        while True:
            try:
                request = connection.recv()
            except EOFError:
                break
            try:
                operation = request["operation"]
                model_name = request["model"]
                if model_name not in models:
                    tok = AutoTokenizer.from_pretrained(
                        model_name, cache_dir=cache_dir, padding_side="left"
                    )
                    factory = AutoModel if operation == "embed" else AutoModelForCausalLM
                    model = (
                        factory.from_pretrained(
                            model_name,
                            cache_dir=cache_dir,
                            torch_dtype=dtype,
                            attn_implementation="sdpa",
                        )
                        .to(device)
                        .eval()
                    )
                    models[model_name] = (tok, model)
                tok, model = models[model_name]
                limit = int(request.get("max_tokens", 8192))
                batch_size = int(request.get("batch_size", 4))
                texts = request["texts"]
                result = []
                for start in range(0, len(texts), batch_size):
                    batch = texts[start : start + batch_size]
                    if operation == "rerank":
                        prefix = (
                            "<|im_start|>system\nJudge whether the Document meets the requirements "
                            "based on the Query and the Instruct provided. Note that the answer "
                            'can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
                        )
                        suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
                        instruction = request["instruction"]
                        query = request["query"]
                        batch = [
                            f"{prefix}<Instruct>: {instruction}\n<Query>: {query}\n"
                            f"<Document>: {text}{suffix}"
                            for text in batch
                        ]
                    inputs = tok(batch, padding=True, truncation=False, return_tensors="pt")
                    if inputs["input_ids"].shape[1] > limit:
                        raise ValueError(
                            f"Local model input exceeds {limit} tokens including its template; "
                            "reduce chunk size or raise the explicit input budget."
                        )
                    inputs = {k: v.to(device) for k, v in inputs.items()}
                    with torch.inference_mode():
                        if operation == "embed":
                            output = model(**inputs, use_cache=False)
                            # Left padding makes the final token the final non-padding token.
                            vectors = torch.nn.functional.normalize(
                                output.last_hidden_state[:, -1].float(), p=2, dim=1
                            )
                            result.extend(vectors.cpu().tolist())
                        else:
                            output = model(**inputs, use_cache=False, logits_to_keep=1)
                            ids = [
                                tok.convert_tokens_to_ids("no"),
                                tok.convert_tokens_to_ids("yes"),
                            ]
                            scores = output.logits[:, -1, ids].float().softmax(dim=-1)[:, 1]
                            result.extend(scores.cpu().tolist())
                    del inputs, output
                status = {
                    "device": device,
                    "models": list(models),
                    "allocated_bytes": torch.cuda.memory_allocated() if device == "cuda" else 0,
                    "torch_version": torch.__version__,
                }
                connection.send({"ok": True, "result": result, "status": status})
            except Exception as exc:
                connection.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:
        try:
            connection.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        except (BrokenPipeError, OSError):
            pass
    finally:
        connection.close()
