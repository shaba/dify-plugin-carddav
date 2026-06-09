# tools

Each tool is a pair: `<tool>.yaml` (identity + description.llm + parameters) and
`<tool>.py` (`class <Tool>(Tool)` with `_invoke(...) -> Generator[ToolInvokeMessage]`).
Register every tool in `provider/carddav.yaml` under `tools:`. The tools are thin
adapters over the `carddav_client` package.
