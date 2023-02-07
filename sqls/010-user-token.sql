create table user_token (
  user_id bigint not null primary key,
  access_token varchar(256) not null,
  expires_in int not null,
  refresh_token varchar(256) not null,
  scope text not null,
  token_type varchar(64) not null,
  last_update double precision not null,
  verified_server_id bigint
);