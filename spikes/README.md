# Phase 0 spikes

This directory contains disposable experiments for uncertain external behavior.
Spikes may duplicate code and use direct scripts, but they must:

- answer one written question;
- record the exact environment and command;
- emit measurements that can be compared;
- restore terminal state in `finally` blocks;
- never be imported by the production package.

Human-readable conclusions are committed under `spikes/results/`. Large raw JSON,
CSV, and logs are ignored and should be reproducible from the probe scripts.
