# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Repository scaffolding, requirements, architecture and decision records.
- Data layer: SQL migrations, XM / Open-Meteo / NOAA clients with retries, pandera validation, idempotent loading and the `voltia` CLI (`migrate`, `backfill`, `update`, `status`).
- Handling of unsettled newest days reported by XM (ADR 0009).
