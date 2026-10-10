# W2: pilot occurrence pipeline

Status log (newest first). Tags: **[V: how]** verified by the named run or command, **[U]** unverified.

- 2026-10-10 17:50 UTC: started. Read spikes A, C, D and the roadmap. Resolved the 6 missing taxon keys with the GBIF match API (all EXACT, ACCEPTED, SPECIES) and checked the 19 given keys (all equal) [V: GBIF /species/match from the sandbox, saved in `data/species/native/pilot_taxa_resolved.csv`].
- Finding: the Claude sandbox CAN reach api.gbif.org, download.gbif.org, sftp.kew.org (WCVP) and raw.githubusercontent.com (Natural Earth, TDWG), contrary to the brief; only the authenticated download requests need the Actions secrets [V: curl/requests from the sandbox, 10 Oct 2026]. Spike A's cached downloads (erase date 2027-04-06) can be refetched and processed locally.
- Finding: the monarch "duplicate" step is explained, see section 4 [V: local analysis of download 0013296-260928105237408].

(Method, per-species tables, native-mask report, DOIs, loading instructions: to be filled in as the runs finish.)
