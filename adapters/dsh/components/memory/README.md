# Optional memory capability

Install this package independently from `@thaliris/dsh-plugin`. Its default Cordis service is `thalirisMemory`. Core and routing do not inject it.

A trusted provider plugin injects `thalirisMemory` and calls `ctx.thalirisMemory.register(ctx, provider)`. Registration/disposal is a native effect. The provider has stable `id`, optional display `name`, and async `read(request)`, `search(request)`, `write(request)` methods returning JSON values. Requests carry native `workspaceId`, canonical `root`, an `AbortSignal`, `maxBytes`, and selected operation arguments (`key`; `query`/`limit`; or `key`/`text`/`provenance`). Providers own transport and credentials. They should observe cancellation and provide their own write idempotency as needed. No provider is revived after removal.

User policy/grants are enforced by the host plugin before invoking this capability. No memory is retrieved automatically. Removing this service disposes dependent providers and leaves native tasks available.
