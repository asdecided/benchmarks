---
schema_version: 1
id: GAB-7826516B3157
type: design
tags: [reading]
---
# Reader View

## Status

Accepted

## Context

Contributors write in a dense editing surface, but most visitors only read, and the editing chrome distracts them.

## User Need

A reader wants the page content with nothing but a table of contents and a search box.

## Design

Signed-out visitors and readers without edit rights get a chromeless view: content column, floating table of contents, search box. Edit controls appear only with edit rights.

## Constraints

The reader view must render from the same document model as the editor; no separate rendering pipeline.

## Rationale

One document model with conditional chrome keeps reading fast without forking the renderer.
