#!/usr/bin/env bash
# Download The Perovskite Database (Archive) v1.0.1 (Zenodo doi 10.5281/zenodo.5837035, CC BY 4.0) and check it.
# The 85 MB CSV is not committed. Usage: bash scripts/get_perovskite_db.sh <dir>
set -euo pipefail
D="${1:?dir}"; mkdir -p "$D"; cd "$D"
curl -sL -o pdb.zip "https://zenodo.org/records/5837035/files/Jesperkemist/perovskitedatabase_data-v1.0.1.zip?download=1"
echo "1119f05607ebe4bbf46ad7cc3258c6b0  pdb.zip" | md5sum -c -
python -c "import zipfile;z=zipfile.ZipFile('pdb.zip');n=[x for x in z.namelist() if x.endswith('.csv')][0];open('Perovskite_database_content_all_data.csv','wb').write(z.read(n))"
sha256sum Perovskite_database_content_all_data.csv
