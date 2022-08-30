#!/bin/bash
pg_dump -Fc --no-acl --no-owner -h localhost -U thanatos verify > verify.dump
