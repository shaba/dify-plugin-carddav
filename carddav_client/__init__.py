"""Pure CardDAV plugin core: DAV discovery, address book listing, vCard parsing/formatting.

No dify_plugin dependency; HTTP is injected so the package is unit-testable with mocked
multistatus XML and vCard strings.
"""
