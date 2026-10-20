# Granite 4.2 8B in the local llama-swap gateway

The gateway at `http://127.0.0.1:8000/v1` advertises `granite-4.2-8b` and the
alias `ibm-granite/granite-4.2-8b`. This serves the pinned upstream BF16 model
downloaded for the comparison experiment, using the existing qualified vLLM
image. Its Apache-2.0 model license and revision are recorded in
`../models.yaml`. No conversion to GGUF or additional download is needed.

1. Merge `granite42-model.yaml` into the existing
   `~/.config/llama-swap/config.yaml`. Keep the existing model entries. The
   installed 2026-10-21 configuration was backed up to
   `config.yaml.bak-granite42-20261021` before this entry was added.

2. Copy `granite42-vllm.container` to
   `~/.config/containers/systemd/granite42-vllm.container`. Its volume refers to
   this checkout's verified local download; adjust that path if the checkout
   moves. The image ID is pinned to the locally qualified GB10 vLLM image.

   ```sh
   systemctl --user daemon-reload
   systemctl --user start granite42-vllm.service
   ```

   This also starts `llama-swap.service`. The backend shares the gateway's
   network namespace and listens at its private loopback port 18102, so the
   existing localhost gateway port remains the entrypoint. Like the existing
   long-context proxy entry, this is a persistent vLLM backend: unloading the
   gateway's placeholder process does not evict its weights. The companion
   service follows gateway stop/restart operations.

3. Request the model through the gateway:

   ```sh
   curl http://127.0.0.1:8000/v1/chat/completions \
     -H 'Content-Type: application/json' \
     -d '{"model":"granite-4.2-8b","messages":[{"role":"user","content":"Hello"}],"max_tokens":128,"chat_template_kwargs":{"enable_thinking":false}}'
   ```

   You should see a real generated assistant response. The first request waits
   for model loading; `/v1/models` lists the entry before it is ready. The
   backend has a 16,384-token context, automatic tool calling with
   `qwen3_coder`, and the built-in `nemotron_v3` reasoning parser supported by
   IBM's model card. It uses offline Hugging Face settings and the exact local
   weights whose four shard hashes were checked before integration.

4. Check live state and logs when needed:

   ```sh
   systemctl --user status llama-swap.service granite42-vllm.service
   podman logs llama-vllm-granite42
   ```

   The ongoing benchmark uses its separate direct vLLM endpoint. These gateway
   smoke requests are not benchmark tasks or evidence of a fine-tuning gain.

Verified on 2026-10-21 through `http://127.0.0.1:8000`: model discovery reports
Granite loaded with a 16,384-token context; the model-name chat request returned
`Granite is ready.` with finish reason `stop`; the Hugging Face alias request
returned an `echo` tool call with arguments `{"message":"ready"}`. Raw local
receipts are `training/unsloth/out/granite42-llama-swap-smoke.json` and
`training/unsloth/out/granite42-llama-swap-tool-smoke.json`. Both systemd units
were active. The original Qwen evaluation process continued throughout setup.
