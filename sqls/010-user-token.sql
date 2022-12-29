create table user_token (
  user_id bigint not null primary key,
  access_token text not null,
  expires_in int not null,
  refresh_token text not null,
  scope text not null,
  token_type text not null,
  last_update real not null,
  verified_server_id bigint
);