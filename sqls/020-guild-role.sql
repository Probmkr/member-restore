drop table if exists guild_role;

create table guild_role (
  guild_id bigint unsigned not null primary key,
  role bigint unsigned not null
);