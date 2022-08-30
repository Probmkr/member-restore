#!/bin/bash
pg_restore --verbose --clean --no-acl --no-owner -d ${1:-$DATABASE_URL} verify.dump
