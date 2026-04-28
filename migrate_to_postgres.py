import sqlite3
import os
import psycopg2
from psycopg2.extras import execute_values

# Connexion à SQLite (adapte le nom de fichier : 'site.db' ou 'marketai.db')
sqlite_conn = sqlite3.connect('site.db')
sqlite_cur = sqlite_conn.cursor()

# Demander l'URL PostgreSQL (tu peux aussi la mettre directement en variable d'env)
db_url = input("Collez l'URL de base de données interne PostgreSQL de Render : ").strip()
db_url = db_url.replace('postgres://', 'postgresql://')

pg_conn = psycopg2.connect(db_url)
pg_cur = pg_conn.cursor()

# Désactiver temporairement les contraintes de clés étrangères
pg_cur.execute("SET session_replication_role = 'replica';")

tables = ['item', 'order', 'order_item']

for table in tables:
    sqlite_cur.execute(f"SELECT * FROM {table}")
    rows = sqlite_cur.fetchall()
    if not rows:
        print(f"Table {table} : vide, ignorée")
        continue
    # Récupérer les noms des colonnes
    col_names = [desc[0] for desc in sqlite_cur.description]
    placeholders = ','.join(['%s'] * len(col_names))
    # Vider la table PostgreSQL
    pg_cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
    # Insertion
    execute_values(pg_cur, f"INSERT INTO {table} ({','.join(col_names)}) VALUES %s", rows)
    pg_conn.commit()
    print(f"✅ {table} : {len(rows)} lignes migrées")

# Réactiver les contraintes
pg_cur.execute("SET session_replication_role = 'origin';")
pg_conn.commit()
sqlite_conn.close()
pg_conn.close()
print("🎉 Migration terminée avec succès.")