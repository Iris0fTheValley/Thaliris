# Optional local memory provider

Install independently with `@thaliris/dsh-memory` and native `storageDomain`. The default provider ID is `thaliris-local`; `providerId` is configurable. The domain `thaliris_memory_local` stores explicit text/key/provenance records scoped to native Workspace IDs. Search is bounded text matching; there is no embedding, vector or RAG engine.

The runtime defaults memory disabled. Explicit user grants and write policy are required. Native plugin removal unregisters the provider and closes its domain; records remain in the configured native storage backend. Core tasks and routing do not depend on this package. A deployment may replace it with any compatible async provider plugin.
