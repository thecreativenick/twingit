# twingit

A Git implementation in pure Python whose repositories real git can't tell apart. Real
`git` should be able to fsck, log, clone and merge anything twingit writes, and the other
way round.

## Status

Early scaffold. Done so far:

- `Repo.init()` creates a `.git` layout real git accepts.
- Loose objects (blob, tree, commit) written and read in git's exact zlib format and SHA-1 naming.
- `write_tree()` snapshots a working directory with git's tree-entry sort order; tests check it
  produces the same tree id as `git write-tree`.
- Commits, refs, `HEAD` resolution and first-parent `log()`. Tests run `git fsck --strict`
  and `git log` on repos twingit created.

## Planned milestones

1. The index (`.git/index` v2): `add`, `status`, `diff` against HEAD and the working tree.
2. `branch`, `checkout`, `reset`, tags; reading packed refs.
3. Packfiles: read and write `.pack`/`.idx` v2, including OFS/REF delta decoding and a delta encoder.
4. `merge` (three-way, recursive merge base, conflict markers byte-identical to git) and `rebase`.
5. `clone`, `fetch` and `push` over `file://` using the pack protocol.
6. Localhost page drawing the commit graph, branches and merges.

## Success bar

`git fsck` passes on every repo twingit writes, `log` output matches git on a 10,000-commit
repo, and 2,000 generated command scripts run under both tools yield identical objects, refs
and merge results.

## Development

```bash
pip install -e .[dev]
pytest
```

Tests that compare against real git are skipped if `git` isn't on the PATH.
