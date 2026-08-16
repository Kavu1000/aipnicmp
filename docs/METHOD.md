# How this platform decides what it shows

The methods note lives at **[`web/src/content/METHOD.md`](../web/src/content/METHOD.md)**.

It is kept there rather than here because the platform renders it directly —
the Method page in the left sidebar imports that file, so the page and the
document can never disagree. The web image is built with `web/` as its Docker
context, so a document outside that directory resolves in a local build and is
missing in the container.

Read it there, or open **Method** in the platform.
