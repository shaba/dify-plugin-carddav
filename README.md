# dify-plugin-carddav

A Dify tool plugin for any CardDAV server (Nextcloud, Radicale, …): list address books,
list/search/read contacts, and create new contacts. The target server is configured per
credential via `base_url`, so a single installation works with any CardDAV server.

The plugin speaks WebDAV/CardDAV directly (PROPFIND/REPORT/PUT, RFC 6352): it discovers
the address book home (`current-user-principal` → `addressbook-home-set`), lists address
books, and runs an `addressbook-query` REPORT to fetch vCards. vCards are parsed and built
with [`vobject`](https://github.com/py-vobject/vobject).

## Configuration

- `base_url` (required) — base/discovery URL of the CardDAV server.
  - Nextcloud: `https://example.com/remote.php/dav/`
  - Radicale: the account URL, e.g. `https://example.com/radicale/user/`
- `username` (required) — CardDAV account username.
- `password` (required, secret) — account password or app password.

Validation discovers and lists the account's address books.

## Tools

### Read

- **`list_addressbooks`** — list the address books available to the account (name,
  description).
- **`list_contacts`** — list contacts in an address book (`addressbook` optional; defaults
  to the first available). Returns name, organization, email and phone.
- **`search_contacts`** — find contacts by a name/email substring (`query` required,
  `addressbook` optional).
- **`get_contact`** — full details of one contact (`identifier` = exact UID, exact full
  name, or a unique name/email substring; `addressbook` optional).

### Write

- **`create_contact`** — create a new contact (`full_name` required; `emails`, `phones`,
  `org`, `title`, `addressbook` optional; emails/phones may be comma-separated). Writing
  is gated solely by the server-side permissions of the configured account — there is no
  extra toggle.

## Known limitations

- **Create-only writes.** `create_contact` always mints a fresh UID and PUTs a new
  vCard (`If-None-Match: *`); there is no `update_contact` or `delete_contact`. Re-running
  `create_contact` for the same person creates a duplicate rather than upserting. Editing
  an existing contact is out of scope for this version.
- **Whole-collection reads.** `list_contacts`, `search_contacts` and `get_contact` fetch
  the entire address book (one match-all `addressbook-query` REPORT) and filter
  client-side. This is server-agnostic but pulls and parses every vCard on each call, so
  very large books (thousands of contacts) are slow and memory-heavy. There is no
  pagination or server-side text-match filtering.
- **Match-all query.** The "fetch all" REPORT relies on a portable `addressbook-query`
  filter. A non-conforming server that silently ignores or rejects it would return an
  empty result, which is indistinguishable from a genuinely empty address book; the tools
  report "none found" in both cases.

## Development

```sh
python3 -m pytest -q
ruff check .
yamllint .
```

The CardDAV logic (DAV discovery, multistatus parsing, vCard parse/build, formatting)
lives in the `carddav_client` package, which is independent of the Dify SDK and covered by
unit tests with mocked HTTP (sample multistatus XML and vCard strings). The tool and
provider classes are thin adapters over it.

CardDAV reference: [RFC 6352](https://www.rfc-editor.org/rfc/rfc6352).

## License

Apache-2.0. Copyright © 2026 Alexey Shabalin.

## Repository

<https://github.com/shaba/dify-plugin-carddav> — issues and pull requests welcome.
