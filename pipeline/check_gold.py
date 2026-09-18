import duckdb

con = duckdb.connect("gold/pinewood.duckdb")

tables = con.execute("SHOW TABLES").fetchdf()

print("\nGOLD TABLES")
print("=" * 40)
print(tables.to_string(index=False))

con.close()