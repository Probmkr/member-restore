#!/bin/bash
psql `heroku config:get DATABASE_URL -a ${1:-$HRA}`
