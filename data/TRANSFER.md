# Moving the WWI + ERPNext setup to another machine

**Using the zip (`wwi-transfer.zip`)?** It already holds everything in §1 except the Docker images, laid out as:
- `Agentic_Hackathon/`: the folders from §1
- `erpnext/compose.yml`
- `erpnext/backups/`: the ERPNext backup. **Check this is not empty.**

On the target, unzip it into your home folder:
- `mv wwi-transfer/Agentic_Hackathon ~/`
- `mv wwi-transfer/erpnext ~/`

Then go straight to §4.

Option chosen: **ERPNext backup and restore** (bench backup → copy → bench restore).

**Do this only after the full load has finished** (`ALL_DONE` in `wwi_load/load.log`). A backup taken mid-load is a half-loaded database.

## 1. What to export

| # | What | Path on this machine | Size | Needed? |
|---|---|---|---|---|
| 1 | ERPNext database and files backup | `/home/dheeraj/erpnext/volumes/sites/frontend/private/backups/` (newest set) | ~0.3–1 GB | **Yes** (all the loaded data) |
| 2 | ERPNext setup file | `/home/dheeraj/erpnext/compose.yml` | tiny | **Yes** |
| 3 | WWI package v2 | `/home/dheeraj/Agentic_Hackathon/data/wwi-package-v2-2026-10-08/` | 241 MB | **Yes** (see §5) |
| 4 | ERPNext loader + evidence | `/home/dheeraj/Agentic_Hackathon/data/erpnext-loader/` | 143 MB | **Yes**, for the reconciliation check and the evidence; `build/` can be skipped if you won't reload |
| 5 | Synthetic fixture | inside v2: `wwi-package-v2-2026-10-08/data/synthetic/` | small | Included with #3 |
| 6 | Research notes | `/home/dheeraj/Agentic_Hackathon/research/` | small | Optional |
| 7 | Docker images | (in Docker) `frappe/erpnext:v15.119.3`, `mariadb:10.6`, `redis:6.2-alpine` | ~2 GB | Only if the target has no internet |

**Do not send**
- `Do_not_open/` (private)
- any `.venv/` or conda `env/` folder (rebuild on the target)
- `/home/dheeraj/erpnext/volumes/` raw files (the backup replaces them)
- `/home/dheeraj/llm/` unless the target will run the LLM itself (it has a 24 GB+ GPU). Otherwise keep the LLM here and connect over the LAN using `CONNECT.md`.

## 2. Target machine requirements

- Linux with Docker and Docker Compose v2 (`docker compose version`), user in the `docker` group
- ~10 GB free disk where the volumes will live, ~4 GB RAM for ERPNext
- Port 8081 free (`ss -ltn | grep 8081`)
- Python 3.10+ for the WWI package and `reconcile.py`

## 3. On THIS machine: back up and copy

Set the target once (replace user and host):
```bash
T=user@OTHER_HOST
```

Take the backup:
```bash
docker exec wwi-erpnext-backend-1 bench --site frontend backup --with-files
docker exec wwi-erpnext-backend-1 ls -lt sites/frontend/private/backups | head -5
```
That makes four files with the same timestamp prefix:
- `*-database.sql.gz`
- `*-files.tar` (public files)
- `*-private-files.tar`
- `*-site_config_backup.json`

Copy everything:
```bash
ssh $T 'mkdir -p ~/erpnext/backups ~/Agentic_Hackathon/data'
rsync -avP /home/dheeraj/erpnext/compose.yml                                $T:~/erpnext/
rsync -avP /home/dheeraj/erpnext/volumes/sites/frontend/private/backups/   $T:~/erpnext/backups/
rsync -avP --exclude runtime/ \
      /home/dheeraj/Agentic_Hackathon/data/wwi-package-v2-2026-10-08       $T:~/Agentic_Hackathon/data/
rsync -avP /home/dheeraj/Agentic_Hackathon/data/erpnext-loader     $T:~/Agentic_Hackathon/data/
# optional
rsync -avP /home/dheeraj/Agentic_Hackathon/research /home/dheeraj/Agentic_Hackathon/CLAUDE.md \
           /home/dheeraj/Agentic_Hackathon/problem_statement.md           $T:~/Agentic_Hackathon/
```
`--exclude runtime/` drops the 174 MB Windows runtime. Keep it if the target runs Windows.

If the target has no internet, also send the images:
```bash
docker save frappe/erpnext:v15.119.3 mariadb:10.6 redis:6.2-alpine | gzip > /home/dheeraj/erpnext/images.tgz
rsync -avP /home/dheeraj/erpnext/images.tgz $T:~/erpnext/
# on target: docker load < ~/erpnext/images.tgz
```

## 4. On the TARGET: start ERPNext and restore

1. Create the volume folders:
   ```bash
   cd ~/erpnext
   mkdir -p volumes/{sites,logs,db-data,redis-queue-data} && chmod 777 volumes/*
   ```
2. Point `compose.yml` at this machine's home folder. Its last four lines bind to `/home/dheeraj/erpnext/volumes/...`.
   ```bash
   sed -i "s#/home/dheeraj/erpnext#$HOME/erpnext#g" compose.yml
   grep device: compose.yml        # check the 4 paths
   ```
3. Start it. The first start creates an empty site called `frontend`, which takes about 5 minutes.
   ```bash
   docker compose -p wwi-erpnext -f compose.yml up -d
   docker compose -p wwi-erpnext logs -f create-site   # wait until it exits
   ```
4. Restore the backup over the empty site:
   ```bash
   P=$(ls backups/*-database.sql.gz | tail -1 | xargs basename | sed 's/-database.sql.gz//')
   docker cp backups/. wwi-erpnext-backend-1:/tmp/bk/
   docker exec wwi-erpnext-backend-1 bench --site frontend restore /tmp/bk/$P-database.sql.gz \
        --with-public-files /tmp/bk/$P-files.tar \
        --with-private-files /tmp/bk/$P-private-files.tar \
        --db-root-password admin --force
   docker exec wwi-erpnext-backend-1 bench --site frontend migrate
   docker compose -p wwi-erpnext restart
   ```
   The restore takes about 10–30 minutes for the full history.
5. Open `http://127.0.0.1:8081` and log in as `Administrator` / `admin`.
   - To reach it from other machines, change `127.0.0.1:8081:8080` to `8081:8080` in `compose.yml` and run `up -d` again.

## 5. Should the WWI package v2 go too? Yes

- `erpnext-loader/reconcile.py` imports `oracle_v2.py` from `../wwi-package-v2-2026-10-08/scripts` and reads its `data/raw/*.parquet`. **Keep the two folders side by side** under `data/`.
- It holds our own app (`launch.sh`), the APIs the agents use, the Application Contract, the evaluation tasks and the retrieval set. ERPNext is the "real app" proof; v2 is the scored benchmark.

Set it up on the target:
```bash
cd ~/Agentic_Hackathon/data/wwi-package-v2-2026-10-08
./setup_linux.sh          # builds .venv from requirements-lock.txt
./launch.sh               # starts our app
python scripts/validate_v2.py
```

## 6. Verify the move

Run the measures inside ERPNext, then compare them with the oracle:
```bash
docker cp ~/Agentic_Hackathon/data/erpnext-loader/erp_measures.py wwi-erpnext-backend-1:/home/frappe/frappe-bench/sites/wwi_load/
docker exec -w /home/frappe/frappe-bench/sites wwi-erpnext-backend-1 ../env/bin/python wwi_load/erp_measures.py
docker cp wwi-erpnext-backend-1:/home/frappe/frappe-bench/sites/wwi_load/erp_measures.json ~/Agentic_Hackathon/data/erpnext-loader/build/
cd ~/Agentic_Hackathon/data/erpnext-loader
../wwi-package-v2-2026-10-08/.venv/bin/python reconcile_feb2016.py   # the standard: data through 2016-02-24
```
`reconcile.py` needs duckdb, which v2's `.venv` provides.

Expected counts:
- Sales Orders 73,596 (73,595 WWI + 1 synthetic)
- Sales Invoices 64,500 (through 24 Feb 2016)
- Purchase Orders 2,074
- Purchase Receipts 1,914 (through 24 Feb 2016)
- all 8 checks PASS in `reconcile_feb2016.py`. The older `reconcile.py` compares against all history to 31 May 2016, so it fails on purpose for Feb–May 2016 invoices and receipts. Ignore it.

## 7. Security

- The ERPNext passwords are the defaults: Administrator `admin`, MariaDB root `admin`, and the loader user `wwi-loader-change-me`. If the target is shared, change them:
  - `bench --site frontend set-admin-password <new>`
  - the loader user's password, under User → wwi-loader
- If you send `/home/dheeraj/llm/` (`api_key.txt`, `CONNECT.md`), the API key travels with it. Use only SSH or rsync, never chat or email.
