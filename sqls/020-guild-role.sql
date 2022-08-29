drop table if exists guild_role;

create table guild_role (
  guild_id bigserial not null primary key,
  role bigserial not null
);