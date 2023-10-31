"""
Download public whips database dumps, convert it to parquet files
"""


import bz2
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pandas as pd
import requests
import rich
from tqdm import tqdm


def download_url_to_file(url: str, filepath: Path) -> Path:
    """
    Given a url
    """
    with requests.get(url, stream=True, timeout=60) as r:  # type: ignore
        r.raise_for_status()
        rich.print(f"Downloading [green]{url}[/green] to [green]{filepath}[/green]")
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return filepath


def unzip_zip_file(zip_file: Path, output_dir: Path) -> Path:
    """
    Given a bz2 file, unzip it to the output_dir
    """
    rich.print(f"Unzipping [green]{zip_file}[/green] to [green]{output_dir}[/green]")
    filepath = output_dir / zip_file.stem
    with bz2.BZ2File(zip_file) as fr, open(filepath, "wb") as fw:
        shutil.copyfileobj(fr, fw)
    return filepath


def convert_to_sqlite(input_file: Path, output_file: Path) -> Path:
    """
    run the mysql2sqlite shell utility on the input file
    """
    rich.print("Converting from [green]mysql[/green] to [green]sqlite[/green]")
    converted_pp = subprocess.run(
        ["src/publicwhip_data/mysql2sqlite", str(input_file)],
        check=True,
        stdout=subprocess.PIPE,
    )

    rich.print(
        f"Converting [green]{input_file}[/green] to [green]{output_file}[/green]"
    )
    conn = sqlite3.connect(output_file)
    conn.executescript(converted_pp.stdout.decode("ISO-8859-1"))
    conn.commit()
    conn.close()

    return output_file


def convert_bz2_mysql_to_paraquet(url: str, output_dir: Path) -> list[Path]:
    """
    Fetch the bz2 file, unzip it, convert it to sqlite, convert it to parquet
    """
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / url.split("/")[-1]
    download_url_to_file(url, output_file)
    result = unzip_zip_file(output_file, output_dir)
    db_filename = output_dir / (
        Path(url.split("/")[-1]).stem.removesuffix(".sql") + ".db"
    )
    if db_filename.exists():
        db_filename.unlink()
    convert_to_sqlite(result, db_filename)
    files = convert_sqlitedb_to_paraquet(db_filename)
    output_file.unlink()
    result.unlink()
    db_filename.unlink()
    return files


def convert_sqlitedb_to_paraquet(input_path: Path) -> list[Path]:
    """
    Convert the sqlite db to a parquet file
    """
    rich.print(
        f"Converting [green]{input_path}[/green] to [green]parquet files[/green]"
    )
    conn = sqlite3.connect(input_path)
    # for all tables in the db
    outputs: list[Path] = []
    for table in conn.execute("SELECT name FROM sqlite_master WHERE type='table';"):
        if table[0] == "sqlite_sequence":
            continue
        # 7.3+0.3+0.2+5.9
        # get the size of a dataframe, chunk it into 1000 rows chunks and reassemble
        count = conn.execute(f"SELECT COUNT(*) FROM {table[0]};").fetchone()[0]
        rich.print(f"Converting {table[0]} with {count} rows")
        dfs: list[pd.DataFrame] = []
        for i in tqdm(range(0, count, 1000)):
            df = pd.read_sql_query(
                f"SELECT * from {table[0]} limit 1000 offset {i}", conn
            )
            dfs.append(df)
        df = pd.concat(dfs)  # type: ignore
        output_filename: Path = input_path.parent / f"{table[0]}.parquet"
        df.to_parquet(output_filename)
        outputs.append(output_filename)
    conn.close()
    return outputs


def fetch_public_whip():
    """
    Convert public whip files into parquet files
    """

    urls = [
        "https://www.publicwhip.org.uk/data/pw_static_tables.sql.bz2",
        "https://www.publicwhip.org.uk/data/pw_dynamic_tables.sql.bz2",
    ]
    for url in urls:
        convert_bz2_mysql_to_paraquet(url, Path("data", "raw"))


def move_files():
    """
    Move the files to the data directory
    """
    for file in Path("data", "raw").glob("*.parquet"):
        shutil.copyfile(file, Path("data", "packages", "public_whip_data", file.name))


def fetch_and_move_pw():
    fetch_public_whip()
    move_files()


if __name__ == "__main__":
    fetch_and_move_pw()
