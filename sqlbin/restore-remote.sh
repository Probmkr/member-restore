#!/bin/bash
pg_restore --verbose --clean --no-acl --no-owner -d `heroku config:get DATABASE_URL -a ${1:-$HRA}` verify.dump
