drop table if exists user_token;

create table user_token (
  user_id bigserial not null primary key,
  access_token text not null,
  expires_in serial not null,
  refresh_token text not null,
  scope text not null,
  token_type text not null,
  last_update real not null
);