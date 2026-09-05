# Design

Thaliris Core is a deterministic, Git-native information topology layer. It
stores bounded task state and evidence, projects the right facts to each
semantic role, and preserves useful material without automatically propagating
every working-set detail.

## Core Responsibilities

- task state with revision-checked CAS and atomic recovery;
- bounded Controller packets;
- semantic role projections for controller, investigator, curator,
  reasoning-specialist, implementer, and reviewer;
- evidence confidence and freshness;
- external artifact pointers whose contents are never implicitly projected;
- project memory and milestone routing;
- explicit, bounded durable promotion;
- Git truth for changed surface and deterministic verification.

Working set is not handoff set. Retention is not propagation. A Controller
packet contains task identity, active work, pending results, unresolved
questions, accepted constraints and decisions, modification boundary,
verification target, and artifact pointers. Raw findings, review bodies,
evidence registries, logs, transcripts, source dumps, and artifact contents are
explicit diagnostic or external paths, not normal routing data.

## Runtime Boundary

Core does not execute agents or define a concrete runtime's lifecycle, child
creation, hooks, transport, or session semantics. Runtime adapters map these
projections to native mechanisms without redefining Core state or role meaning.

## Persistence

The task whiteboard remains `.context/state.json`. Artifact registration is
explicit and path-safe; registration validates an existing repository-local
regular file, while later disappearance does not invalidate task state. Durable
promotion is explicit, evidence-backed, bounded, and CAS-protected. Core
mutations use one lock, one coherent backup, atomic replacement, and guarded
rollback.
