create table letoa_user_types (
  type_id serial not null primary key,
  type_name varchar(32),
  type_name_jp varchar(32)
);

insert into letoa_user_types (type_name, type_name_jp) values
('normal_backup', 'ノーマル'),
('pro', 'プロ'),
('ultimate', 'アルティメット'),
('developer', 'デベロッパー'),
('admin', '最高権限者');