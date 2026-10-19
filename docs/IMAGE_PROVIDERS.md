# Cinematic image providers

Checked 2026-10-19. This is research, not a list of configured providers.

| Provider | Free access | Setup and practical fit |
| --- | --- | --- |
| AI Horde | Community service; anonymous requests supported without registration | Lowest-priority queues; anonymous service may be restricted under load. Model availability varies. First candidate for zero-fee API automation. |
| Cloudflare Workers AI | 10,000 Neurons/day on Workers Free | Account ID and Workers AI token required. Requests stop at the Free-plan allowance. Keep the account on Free; a local request limit cannot prevent charges if someone changes the account to Paid. |
| Pollinations | Earned Quest Pollen where eligible; paid Pollen also available | Generation requires a key and sufficient balance. Current official docs do not promise unlimited anonymous free generation. |
| ComfyUI | Open-source local API, no hosted inference fee | Requires model downloads and local compute. CPU operation supported; speed on this Iris Xe PC has not been benchmarked. Optional paid API nodes are separate from local generation. |
| Hugging Face Inference Providers | $0.10/month for free accounts, subject to change | Token required, very small experimentation allowance. Extra usage requires credits. |

A free GitHub repository is not necessarily a free hosted inference service.
Cloudflare proxies inherit Cloudflare's limits; clients for paid services inherit
those services' billing. Do not install unreviewed cookie/token extraction proxies.
Model licenses and provider terms must be recorded with generated assets; a source
code license alone does not establish the rights to every hosted model or output.

## Evidence

- AI Horde repository and anonymous access:
  https://github.com/Haidra-Org/AI-Horde
- API integration lifecycle:
  https://github.com/Haidra-Org/AI-Horde/blob/main/README_integration.md
- Read-only live check: GET https://aihorde.net/api/v2/status/models?type=image
  returned HTTP 200 and available model/worker entries. No image was generated via
  this API, so latency, output quality and actual anonymous admission remain untested.
- Cloudflare pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Official Cloudflare image example on GitHub:
  https://github.com/cloudflare/workers-mcp/blob/main/examples/02-image-generation/src/index.ts
- FLUX model API: https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/
- Pollinations credit/authentication rules:
  https://github.com/pollinations/pollinations/blob/main/enter.pollinations.ai/POLLEN_FAQ.md
- Pollinations public image catalogue returned HTTP 200 (91 model entries).
  Catalogue availability is not proof that generation is free or authorized.
- ComfyUI: https://github.com/Comfy-Org/ComfyUI
- Hugging Face credits: https://huggingface.co/docs/inference-providers/pricing

## Google AI Pro

The subscription gives image-generation access in Gemini/Flow and higher limits
in the AI Studio interface. API usage tiers are separate:
https://ai.google.dev/gemini-api/docs/google-ai-plans

Current Google documentation also lists $10/month Google Cloud credits through
its developer benefit. Activation and a billing account are required. Vertex AI
is an eligible Cloud service; benefits do not make arbitrary API usage unlimited:
https://developers.google.com/profile/help/benefits

A signed-in browser can assist with website generation, but this is not a supported
subscription API integration. Login checks, changed controls, and download access
can interrupt automation. Do not reuse private website endpoints or extract cookies
as API credentials. No such connector is currently implemented in SelahFrame.

## Flow sample generated during research

The user explicitly asked to explore their Google AI Pro benefits, so the Flow UI
was used rather than the default built-in image-generation path. Three separate
9:16 stills were generated with the UI reporting Nano Banana 2.1. No videos or
music were requested. The browser's download approval was declined; images remain
in Flow and have not been imported into SelahFrame.

Project: https://flow.google.com/project/50f9f1b7-7914-4a86-a022-f2c44f320ac3

Prompt set:

1. A distant ancient Judean shepherd guiding a small flock along rolling hills at
   sunrise, wide establishing composition.
2. Sheep resting naturally in lush green pasture, ground-level detail and soft
   morning light.
3. A quiet clear stream beside green banks, gentle reflections, a peaceful
   landscape with no people.

Shared style: cinematic photorealistic stills inspired by Psalm 23:1–2, portrait
9:16, one separate image per shot, consistent warm natural morning light, realistic
wool/grass/stone/water textures. Illustrative interpretations, not a documented
historical event. No scripture lettering, logos, added watermark, collage, or panel
borders. Preserve any provenance marks supplied by the provider.
