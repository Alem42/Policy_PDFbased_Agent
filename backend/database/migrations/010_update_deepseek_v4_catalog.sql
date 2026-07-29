-- Migration 010: replace DeepSeek's discontinued legacy model aliases with V4.

DELETE FROM public.model_catalog
WHERE provider = 'deepseek'
  AND capability = 'chat'
  AND model IN ('deepseek-chat', 'deepseek-reasoner');

INSERT INTO public.model_catalog (
    id, provider, provider_label, capability, model, base_url, endpoint,
    dimensions, openai_compatible, notes, sort_order
)
VALUES
    (
        gen_random_uuid(), 'deepseek', 'DeepSeek', 'chat',
        'deepseek-v4-flash', 'https://api.deepseek.com', '/chat/completions',
        NULL, true, 'Supports thinking and non-thinking modes', 100
    ),
    (
        gen_random_uuid(), 'deepseek', 'DeepSeek', 'chat',
        'deepseek-v4-pro', 'https://api.deepseek.com', '/chat/completions',
        NULL, true, 'Supports thinking and non-thinking modes', 101
    )
ON CONFLICT (provider, capability, model) DO UPDATE
SET provider_label = EXCLUDED.provider_label,
    base_url = EXCLUDED.base_url,
    endpoint = EXCLUDED.endpoint,
    dimensions = EXCLUDED.dimensions,
    openai_compatible = EXCLUDED.openai_compatible,
    notes = EXCLUDED.notes;
