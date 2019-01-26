create table trackscrobbles
(
	id serial not null
		constraint trackscrobbles_pkey
			primary key,
	date timestamp not null,
	name text,
	artist text,
	album text,
	tick text not null
)
;

create unique index trackscrobbles_id_uindex
	on trackscrobbles (id)
;

create unique index trackscrobbles_date_uindex
	on trackscrobbles (date)
;

create unique index trackscrobbles_tick_uindex
	on trackscrobbles (tick)
;

