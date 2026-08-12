# Claude Desktop compatibility trial prompt

After registering the reviewed `soundfetch mcp` command in Claude Desktop,
paste the following prompt into a new conversation:

```text
Run a manual Soundfetch MCP compatibility trial. Do not download any files.

1. Call `list_sources`.
2. Call `check_provider_status` for `archive`.
3. Call `search_sounds` using:
   - provider: archive
   - query: rain
   - max_results: 1

Verify that:
- all Soundfetch tools are discoverable;
- each call returns structured, readable results;
- the search returns at most one result;
- progress or logging does not corrupt the structured response;
- no unexpected files are created.

Then report:
- Claude Desktop version and operating system;
- timestamp;
- success/failure for tool discovery, provider status, and bounded search;
- exact errors or unexpected behavior;
- whether Soundfetch appears safe to advertise as Claude Desktop compatible.

Do not claim success for any call that did not actually complete.
```

Record these candidate identifiers alongside the response:

- Git commit: `b1ace99bffe3ce2b553244100010045c739e47fb`
- Wheel: `soundfetch-0.4.0-py3-none-any.whl`
- Wheel SHA-256:
  `7960914a429d41dcdafa6773141444a57b83e0990fec33fe9d8d8816a0e4534f`

Copy the results into the manual-trial table in
`docs/beta-readiness-0.4.0.md`. Do not include credentials, local configuration
secrets, or unrelated host logs.
