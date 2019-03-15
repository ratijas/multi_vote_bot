select p.id, p.owner_id, p.topic, a.txt, count(a.id) as votes
from polls p
join answers a
	on a.poll_id = p.id
join votes v
	on v.answer_id = a.id
group by a.id
order by p.id, a.id
