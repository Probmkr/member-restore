create table letoa_user (
  user_secret_id bigserial not null primary key,
  user_id varchar(32) not null,
  user_discord_id bigint not null,
  user_password bytea,
  user_type_id int references letoa_user_types (type_id) default 1,
  created_date timestamp not null default current_timestamp
);
