#!/bin/bash
app=${1:-$HRA}
heroku pg:backups:capture -a $app
heroku pg:backups:download -a $app
