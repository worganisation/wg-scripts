# wg-scripts

Raspberry Pi services for MQTT, GPIO, DHT22, and system stats.

## Development

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
```

Install [prek](https://github.com/j178/prek) hooks:

```bash
uv tool install prek
prek install
```

Common just recipes:

```bash
just setup              # sync all dependency groups
just run mqtt_gpio      # run a service locally
just sync               # runtime deps only (Pi deploy)
just update             # switch to main, ff-only pull, sync, restart
just deploy 1.3.1          # dirty-check, checkout tag/branch (detached), sync, restart
just deploy feature/smart  # same for a remote branch tip
just setup-tailscale KEY  # install Tailscale and join the tailnet
just setup-deploy-key FILE_OR_LINE  # install CI deploy SSH public key
```

Linting and typechecking are enforced via prek (ruff + basedpyright). Commits
should follow [Conventional Commits](https://www.conventionalcommits.org/);
releases are cut by python-semantic-release on `main`.

## Auto-deploy on release

Manually dispatch Semantic Release on `main` to publish a version. Stable published releases trigger the CC self-hosted Linux runner to deploy that tag over direct LAN SSH. The workflow declares `pi@10.0.0.51` (mtrxpi), `worgarside@10.0.0.241` (vaultpi), and `worgarside@10.0.0.52` (vsmppi). OpenWrt owns these DHCP reservations, and infrastructure owns the runner's TCP 22 allowlist.

The runner invokes `just deploy <tag>` in `/home/<user>/wg-scripts`. Unreachable hosts are warned and skipped; the job fails if no host succeeds. Re-run the original release deployment to retry the same tag, including after powering on an offline Pi. Publish a reviewed revert release for a source rollback. Deployments serialize across releases so two tags cannot update the Pis concurrently.

### One-time Pi setup

Use a verified administrative SSH connection to install the deployment public key:

```fish
just setup-deploy-key ./wg-scripts-deploy.pub
```

`setup-deploy-key` accepts a public key file or key line. Each Pi must have the matching key and the repository at `/home/<user>/wg-scripts`, with `just`, `uv` and `git` available. GCF's `actions/lan-ssh` creates temporary credentials and a strict SSH configuration, then automatically removes them after the job.

### Actions settings

Use the `production-deploy` environment, or repository settings for private repositories on GitHub Free.

| Kind | Name | Notes |
| --- | --- | --- |
| Secret | `DEPLOY_SSH_PRIVATE_KEY` | Private half of the deployment public key installed on each Pi |
| Var | `DEPLOY_SSH_KNOWN_HOSTS` | Independently verified OpenSSH host-key entries for all three LAN addresses |

Verify host keys through an existing trusted administrative connection before enrolling them. Keep vsmppi's verified key configured while it is powered off; deployment never discovers or automatically trusts new keys.
