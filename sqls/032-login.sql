create table letoa_logins (
  user_id varchar(32) not null,
  user_discord_id bigint not null unique,
  loged_out boolean not null default FALSE,
  login_time timestamp not null default current_timestamp,
  logout_time timestamp
);