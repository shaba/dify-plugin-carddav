# Privacy Policy

This plugin (`dify-plugin-carddav`) does not collect, store or transmit any personal
data to the plugin author or any third party.

- The configured credentials are `base_url` (the URL of the CardDAV server you choose),
  `username` and `password`. They are stored by your Dify instance, not by the plugin
  author.
- When you invoke a tool, the plugin sends WebDAV/CardDAV requests (PROPFIND, REPORT, PUT)
  **only** to that `base_url`, carrying the contact data, search query or address book
  selector you provided, authenticated with the configured username and password.
  Requests use the User-Agent `dify-plugin-carddav/0.0.1`.
- No analytics, telemetry or external hosts are involved. The plugin itself persists
  nothing.

Your queries and the contact data you read or create are subject to the privacy policy of
the CardDAV server configured in `base_url`.
