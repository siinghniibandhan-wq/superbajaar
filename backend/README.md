# Backend transition

The active AWS backend was verified by the user as Gunicorn listening on `127.0.0.1:8001`; PostgreSQL listens on `127.0.0.1:5432`. Keep those ports. Do not replace the active process with this scaffold until the new API has feature parity and passes tests. Do not point the new app at production for development tests.

The clean modular entry point is `app.main:app`. When intentionally running it in a test/staging environment on the confirmed port, a compatible command is:

```bash
gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8001
```

Only one process can bind the same IP/port at a time; do not start this beside the currently active service on that same listener. Use a separate staging port until a controlled cutover.
