# Security policy

Please report a security issue through GitHub's private vulnerability reporting for this repository. Do not open a public issue for a secret leak, remote-code path, or data exposure.

Scenario files can read environment variables into request headers. Reports omit header values and full audio bodies, but they retain transcript text and server errors. Store reports as user data, review them before sharing, and keep secrets out of scenario literals.

Only benchmark targets you own or have permission to test. Concurrency and fault runs can create material load.
