---
title: Generational garbage collection pauses
date: 2026-11-12
tags: [compilers, runtime]
---

# Generational garbage collection pauses

A generational collector separates young objects from old ones because most
objects die young. The nursery collects the young generation alone, and that
collection is short precisely because it never visits the old space.

## Write barriers and promotion

An object survives by being copied from the nursery into the old generation, and
promotion is what eventually forces a full collection. The write barrier records
every store of an old object into a young one, so the nursery collection can
trace the remembered set instead of scanning the heap.

Pause time tracks the size of the nursery, not the size of the heap, which is why
tuning the nursery is the first knob for a latency budget. Promotion rate decides
the rest: an application that keeps allocating long-lived objects fills the old
generation and pays for the full collection anyway.
