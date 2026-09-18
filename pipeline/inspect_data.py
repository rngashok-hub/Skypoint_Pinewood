from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

print("=" * 70)
print("PINEWOOD SCHEMA COMPARISON")
print("=" * 70)

files = sorted(DATA_DIR.glob("*.csv"))

schemas = {}

for file in files:

    try:
        df = pd.read_csv(file, nrows=5)

        # Remove month from filename
        source_name = file.stem
        source_name = source_name.rsplit("_", 2)[0]

        columns = tuple(df.columns)

        if source_name not in schemas:
            schemas[source_name] = {}

        schemas[source_name].setdefault(columns, []).append(file.name)

    except Exception as e:
        print(f"ERROR: {file.name}")
        print(e)


for source, schema_versions in schemas.items():

    print("\n" + "-" * 70)
    print(f"SOURCE: {source}")
    print(f"NUMBER OF SCHEMA VERSIONS: {len(schema_versions)}")

    for version_number, (columns, files) in enumerate(
        schema_versions.items(),
        start=1
    ):

        print(f"\nSchema version {version_number}")
        print(f"Files: {len(files)}")

        print("Columns:")

        for column in columns:
            print(f"  - {column}")

        if len(files) <= 6:
            print("Files:")

            for file in files:
                print(f"  - {file}")

print("\n" + "=" * 70)
print("SCHEMA COMPARISON COMPLETE")
print("=" * 70)