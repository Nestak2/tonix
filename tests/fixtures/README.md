# Test fixtures (not published)

The tests marked `needs_fixtures` use four pages saved from Sonix with Firefox
("Save page as", complete page). They hold personal data, so they are not part of
the repository (see `.gitignore`) and those tests are skipped when the files are absent.

To run them, save these pages from your own Sonix account into this folder:

| File | Sonix page |
|---|---|
| `sonix_publications.html` | Научни публикации и цитирания (the list) |
| `sonix_new_publication.html` | Нова публикация (the form) |
| `sonix_cites.html` | Цитирания of one publication that has several citations |
| `sonix_new_cite.html` | Ново цитиране (the form) |

Some expectations in the tests (names, counts) match the author's own pages, so with
other pages a few of them need adjusting.
