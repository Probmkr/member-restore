create table letoa_user (
  user_secret_id bigint not null primary key
  user_id varchar(32) not null,
  password bit(60),
  user_type_id references letoa_user_types (type_id) default 1
);






