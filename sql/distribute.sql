-- Répartition Citus (décision D14), à exécuter sur le coordinateur après sql/schema.sql
-- et après l'ajout des workers (citus_add_node). Tables vides de préférence.

-- Métadonnées : copiées sur chaque worker, pour que les jointures restent locales.
SELECT create_reference_table('stations');
SELECT create_reference_table('batches');

-- Mesures : réparties par hachage de la station (32 shards par défaut).
SELECT create_distributed_table('observations', 'station');

-- Tables liées : même colonne, mêmes shards, mêmes workers que observations.
SELECT create_distributed_table('observations_history', 'station', colocate_with => 'observations');
SELECT create_distributed_table('observations_staging', 'station', colocate_with => 'observations');
SELECT create_distributed_table('monthly_stats',        'station', colocate_with => 'observations');
