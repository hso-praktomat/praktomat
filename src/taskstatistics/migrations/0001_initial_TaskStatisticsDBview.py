# Generated by Django 1.11.29 on 2022-05-31 15:35
# but most parts are written manually. R.H @ H-BRS
# this migration file creates inside the database a view, containing computed datas for using as boxplot-diagram-values.

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tasks', '0001_initial'),
        ('accounts', '0002_add_groups'),
        ('solutions', '0001_initial'),
    ]

    sql_begin_oracle = """
        CREATE OR REPLACE VIEW dbview_tasksstatistic AS
        """
    sql_begin_other = """
        DROP VIEW IF EXISTS dbview_tasksstatistic;
        CREATE VIEW dbview_tasksstatistic AS
        """
    sql_rest = """
        WITH
        rh_task AS
        ( SELECT t.id as task, t.title
          FROM tasks_task t
        ),
        rh_count_submitters_all AS
        ( SELECT s.task_id as task, count(DISTINCT s.author_id) as authors
          FROM solutions_solution s
          GROUP BY s.task_id
        ),
        rh_submitters_passed_finals AS
        ( SELECT DISTINCT s.task_id as task, s.author_id as author
          FROM solutions_solution s
          WHERE s.final = true
          AND s.accepted = true
        ),
        cnt_sub_passed_finals AS
        ( SELECT s.task_id as task, count(DISTINCT s.author_id) as authors
          FROM solutions_solution s
          WHERE s.final = true
          AND s.accepted = true
          GROUP BY s.task_id
        ),
        rh_submitters_failed_finals AS
        ( SELECT DISTINCT s.task_id as task , s.author_id as author
          FROM solutions_solution s
          WHERE s.final = true
          AND s.accepted = false
        ),
        cnt_sub_failed_finals AS
        ( SELECT s.task_id as task, count(DISTINCT s.author_id) as authors
          FROM solutions_solution s
          WHERE s.final = true
          AND s.accepted = false
          GROUP BY s.task_id
        ),
        submitters_latest_not_accepted AS
        ( SELECT DISTINCT s.task_id as task, s.author_id as author
          FROM solutions_solution s
          WHERE (s.task_id , s.author_id) NOT IN (SELECT i.task_id, i.author_id FROM solutions_solution i WHERE i.final = true)
          AND s.final = false
          AND s.accepted = false
        ),
        cnt_sub_latest_not_accepted AS
        ( SELECT s.task_id as task, count(DISTINCT s.author_id) as authors
          FROM solutions_solution s
          WHERE s.final = false
          AND s.accepted = false
          GROUP BY s.task_id
        ),
        rh_count_uploads_all AS
        ( SELECT s.task_id as task, count (DISTINCT s.id) as uploads
          FROM solutions_solution s
          GROUP BY s.task_id
        ),
        rh_count_uploads_accepted AS
        ( SELECT s.task_id as task, count (DISTINCT s.id) as uploads
          FROM solutions_solution s
          WHERE s.accepted = true
          GROUP BY s.task_id
        ),
        rh_count_uploads_rejected AS
        ( SELECT s.task_id as task, count (DISTINCT s.id) as uploads
          FROM solutions_solution s
          WHERE s.accepted = false
          GROUP BY s.task_id
        ),
-- --------------------
        cnt_uploads_per_submitter AS
        ( SELECT s.task_id as task, s.author_id as authors, count(DISTINCT s.id) as uploads
          FROM solutions_solution s
          GROUP BY s.task_id, s.author_id
        ),
-- --------------------
        datatabular_finals_passed AS
        ( SELECT DISTINCT s.task_id as task, s.author_id as author, u.uploads as uploads
          FROM solutions_solution s , cnt_uploads_per_submitter u
          WHERE s.author_id = u.authors
          AND s.task_id = u.task
          AND s.final = true
          AND s.accepted = true
        ),
        sortedPartition_finals_passed AS
        ( SELECT task, author, uploads, ROW_NUMBER() OVER(PARTITION BY o.task ORDER BY o.uploads) as Reihung
          FROM datatabular_finals_passed o
        ) ,
        maxGroupElement_finals_passed AS
        ( SELECT task, max(sP.Reihung) as maxElement
          FROM sortedPartition_finals_passed sP
          GROUP BY task
        ),
        avg_finals_passed AS
        ( Select s.task as task, avg(s.uploads) as avg
          FROM sortedPartition_finals_passed s
          GROUP BY s.task
        ) ,
        q0_finals_passed AS
        ( Select s.task as task, min(s.uploads) as q0
          FROM sortedPartition_finals_passed s
          GROUP BY s.task
        ) ,
        q1_finals_passed AS
        ( SELECT s.task as task, max(s.uploads) as q1
          FROM sortedPartition_finals_passed s, maxGroupElement_finals_passed m
          WHERE s.Reihung <= (0.25 * m.maxElement+1) AND s.task = m.task
          Group By s.task
        ) ,
         -- computing the median:
         -- if maxElement is odd take the value of middle Element
         -- if maxElement is even take the average of both elements around position x.5 (that are x and x+1)
        q2U_finals_passed AS
        (  -- compute the median for case "odd number of values", that is take the middle element.
         SELECT s.task, max(s.uploads) as q2_Median_U
         FROM sortedPartition_finals_passed s, maxGroupElement_finals_passed m
         WHERE s.Reihung <= (0.5 * m.maxElement)+1 AND s.task = m.task
         Group By s.task
        ) ,
        q2G_finals_passed AS
        ( -- compute the median for case "even number of values", that is compute the avg of both middle elements.
         SELECT u.task as task, avg(u.uploads) as q2_Median_G
         FROM
             (
              SELECT task, uploads
              FROM (
                     SELECT s1.task as task, max(s1.uploads) as uploads
                     FROM sortedPartition_finals_passed s1, maxGroupElement_finals_passed m1
                     WHERE s1.Reihung <= (0.5 * m1.maxElement) AND s1.task = m1.task -- lower middle element
                     Group By s1.task
                     UNION
                     SELECT s2.task as task , max(s2.uploads)
                     FROM sortedPartition_finals_passed s2, maxGroupElement_finals_passed m2
                     WHERE s2.Reihung <= (0.5 * m2.maxElement)+1 AND s2.task = m2.task -- heigher middle element
                     Group By s2.task
                    ) u
             ) u
          Group By task
        ) ,
        q2_finals_passed as
        (
           Select distinct t.task as task,
           CASE
             WHEN (SELECT  m.maxElement % 2 From maxGroupElement_finals_passed m WHERE t.task = m.task) = 0
             THEN (SELECT q2G_finals_passed.q2_Median_G FROM q2G_finals_passed WHERE q2G_finals_passed.task = t.task)
             ELSE (SELECT q2U_finals_passed.q2_Median_U FROM q2U_finals_passed WHERE q2U_finals_passed.task = t.task)
             END AS q2
           FROM sortedPartition_finals_passed t
        ) ,
        q3_finals_passed AS
        ( SELECT s.task as task, max(s.uploads) as q3
          FROM sortedPartition_finals_passed s, maxGroupElement_finals_passed m
          WHERE s.Reihung <= (0.75 * m.maxElement+1) AND s.task = m.task
          Group By s.task
        ) ,
        q4_finals_passed AS
        ( Select s.task as task, max(s.uploads) as q4
          FROM sortedPartition_finals_passed s
          GROUP BY s.task
        ),
-- --------------------
        datatabular_finals_failed AS
        ( SELECT DISTINCT s.task_id as task, s.author_id as author, u.uploads as uploads
          FROM solutions_solution s , cnt_uploads_per_submitter u
          WHERE s.author_id = u.authors
          AND s.task_id = u.task
          AND s.final = true
          AND s.accepted = false
        ),
        sortedPartition_finals_failed AS
        ( SELECT task, author, uploads, ROW_NUMBER() OVER(PARTITION BY o.task ORDER BY o.uploads) as Reihung
          FROM datatabular_finals_failed o
        ) ,
        maxGroupElement_finals_failed AS
        ( SELECT task, max(sP.Reihung) as maxElement
          FROM sortedPartition_finals_failed sP
          GROUP BY task
        ),
        avg_finals_failed AS
        ( Select s.task as task, avg(s.uploads) as avg
          FROM sortedPartition_finals_failed s
          GROUP BY s.task
        ) ,
        q0_finals_failed AS
        ( Select s.task as task, min(s.uploads) as q0
        FROM sortedPartition_finals_failed s
        GROUP BY s.task
        ) ,
        q1_finals_failed AS
        ( SELECT s.task as task, max(s.uploads) as q1
          FROM sortedPartition_finals_failed s, maxGroupElement_finals_failed m
          WHERE s.Reihung <= (0.25 * m.maxElement+1) AND s.task = m.task
          Group By s.task
        ) ,
         -- computing the median:
         -- if maxElement is odd take the value of middle Element
         -- if maxElement is even take the average of both elements around position x.5 (that are x and x+1)
        q2U_finals_failed AS
        (  -- compute the median for case "odd number of values", that is take the middle element.
         SELECT s.task, max(s.uploads) as q2_Median_U
         FROM sortedPartition_finals_failed s, maxGroupElement_finals_failed m
         WHERE s.Reihung <= (0.5 * m.maxElement)+1 AND s.task = m.task
         Group By s.task
        ) ,
        q2G_finals_failed AS
        ( -- compute the median for case "even number of values", that is compute the avg of both middle elements.
         SELECT u.task as task, avg(u.uploads) as q2_Median_G
         FROM
             (
              SELECT task, uploads
              FROM (
                     SELECT s1.task as task, max(s1.uploads) as uploads
                     FROM sortedPartition_finals_failed s1, maxGroupElement_finals_failed m1
                     WHERE s1.Reihung <= (0.5 * m1.maxElement) AND s1.task = m1.task -- lower middle element
                     Group By s1.task
                     UNION
                     SELECT s2.task as task , max(s2.uploads)
                     FROM sortedPartition_finals_failed s2, maxGroupElement_finals_failed m2
                     WHERE s2.Reihung <= (0.5 * m2.maxElement)+1 AND s2.task = m2.task -- heigher middle element
                     Group By s2.task
                    ) u
             ) u
          Group By task
        ) ,
        q2_finals_failed as
        (
           Select distinct t.task as task,
           CASE
             WHEN (SELECT  m.maxElement % 2 From maxGroupElement_finals_failed m WHERE t.task = m.task) = 0
             THEN (SELECT q2G_finals_failed.q2_Median_G FROM q2G_finals_failed WHERE q2G_finals_failed.task = t.task)
             ELSE (SELECT q2U_finals_failed.q2_Median_U FROM q2U_finals_failed WHERE q2U_finals_failed.task = t.task)
             END AS q2
           FROM sortedPartition_finals_failed t
        ) ,
        q3_finals_failed AS
        ( SELECT s.task as task, max(s.uploads) as q3
          FROM sortedPartition_finals_failed s, maxGroupElement_finals_failed m
          WHERE s.Reihung <= (0.75 * m.maxElement+1) AND s.task = m.task
          Group By s.task
        ) ,
        q4_finals_failed AS
        ( Select s.task as task, max(s.uploads) as q4
          FROM sortedPartition_finals_failed s
          GROUP BY s.task
        ),
-- --------------------
        datatabular_only_failed AS
        ( SELECT DISTINCT s.task_id as task, s.author_id as author, u.uploads as uploads
          FROM solutions_solution s , cnt_uploads_per_submitter u
          WHERE s.author_id = u.authors
          AND s.task_id = u.task
          AND s.final = false
          AND s.accepted = false
        ),
        sortedPartition_only_failed AS
        ( SELECT task, author, uploads, ROW_NUMBER() OVER(PARTITION BY o.task ORDER BY o.uploads) as Reihung
          FROM datatabular_only_failed o
        ) ,
        maxGroupElement_only_failed AS
        (SELECT task, max(sP.Reihung) as maxElement
        FROM sortedPartition_only_failed sP
        GROUP BY task
        ),
        avg_only_failed AS
        ( Select s.task as task, avg(s.uploads) as avg
          FROM sortedPartition_only_failed s
          GROUP BY s.task
        ) ,
        q0_only_failed AS
        ( Select s.task as task, min(s.uploads) as q0
          FROM sortedPartition_only_failed s
          GROUP BY s.task
        ) ,
        q1_only_failed AS
        ( SELECT s.task as task, max(s.uploads) as q1
          FROM sortedPartition_only_failed s, maxGroupElement_only_failed m
          WHERE s.Reihung <= (0.25 * m.maxElement+1) AND s.task = m.task
          Group By s.task
        ) ,
         -- computing the median:
         -- if maxElement is odd take the value of middle Element
         -- if maxElement is even take the average of both elements around position x.5 (that are x and x+1)
        q2U_only_failed AS
        (  -- compute the median for case "odd number of values", that is take the middle element.
         SELECT s.task, max(s.uploads) as q2_Median_U
         FROM sortedPartition_only_failed s, maxGroupElement_only_failed m
         WHERE s.Reihung <= (0.5 * m.maxElement)+1 AND s.task = m.task
         Group By s.task
        ) ,
        q2G_only_failed AS
        ( -- compute the median for case "even number of values", that is compute the avg of both middle elements.
         SELECT u.task as task, avg(u.uploads) as q2_Median_G
         FROM
             (
              SELECT task, uploads
              FROM (
                     SELECT s1.task as task, max(s1.uploads) as uploads
                     FROM sortedPartition_only_failed s1, maxGroupElement_only_failed m1
                     WHERE s1.Reihung <= (0.5 * m1.maxElement) AND s1.task = m1.task -- lower middle element
                     Group By s1.task
                     UNION
                     SELECT s2.task as task , max(s2.uploads)
                     FROM sortedPartition_only_failed s2, maxGroupElement_only_failed m2
                     WHERE s2.Reihung <= (0.5 * m2.maxElement)+1 AND s2.task = m2.task -- heigher middle element
                     Group By s2.task
                    ) u
             ) u
          Group By task
        ) ,
        q2_only_failed as
        (
           Select distinct t.task as task,
           CASE
             WHEN (SELECT  m.maxElement % 2 From maxGroupElement_only_failed m WHERE t.task = m.task) = 0
             THEN (SELECT q2G_only_failed.q2_Median_G FROM q2G_only_failed WHERE q2G_only_failed.task = t.task)
             ELSE (SELECT q2U_only_failed.q2_Median_U FROM q2U_only_failed WHERE q2U_only_failed.task = t.task)
             END AS q2
           FROM sortedPartition_only_failed t
        ) ,
        q3_only_failed AS
        ( SELECT s.task as task, max(s.uploads) as q3
          FROM sortedPartition_only_failed s, maxGroupElement_only_failed m
          WHERE s.Reihung <= (0.75 * m.maxElement+1) AND s.task = m.task
          Group By s.task
        ) ,
        q4_only_failed AS
        ( Select s.task as task, max(s.uploads) as q4
          FROM sortedPartition_only_failed s
          GROUP BY s.task
        )
        SELECT t.task as id
       ,      t.task as task_id
       ,      t.title as title
       ,      s.authors as submitters_all
       ,      spf.authors as submitters_passed_finals
       ,      sff.authors as submitters_failed_finals
       ,      slna.authors as submitters_latest_not_accepted
       ,      u.uploads as uploads_all
       ,      ua.uploads as uploads_accepted
       ,      ur.uploads as uploads_rejected
       ,      fpavg.avg as avg_upl_until_final_pass
       ,      fpq0.q0 as lo_whisker_upl_til_final_pass
       ,      fpq1.q1 as lo_quart_upl_til_final_pass
       ,      fpq2.q2 as med_upl_til_final_pass
       ,      fpq3.q3 as up_quart_upl_til_final_pass
       ,      fpq4.q4 as up_whisker_upl_until_final_pass
       ,      ffavg.avg as avg_uploads_final_failed
       ,      ffq0.q0 as lo_whisker_upl_final_fail
       ,      ffq1.q1 as lo_quart_upl_final_fail
       ,      ffq2.q2 as median_uploads_final_failed
       ,      ffq3.q3 as up_quart_upl_final_failed
       ,      ffq4.q4 as up_whisker_upl_final_failed
       ,      ofavg.avg as avg_uploads_only_failed
       ,      ofq0.q0 as lo_whisker_upl_only_fail
       ,      ofq1.q1 as lo_quart_upl_only_fail
       ,      ofq2.q2 as median_uploads_only_failed
       ,      ofq3.q3 as up_quart_upl_only_failed
       ,      ofq4.q4 as up_whisker_upl_only_failed
        FROM rh_task t
             LEFT OUTER JOIN rh_count_submitters_all s        ON (t.task = s.task)
             LEFT OUTER JOIN cnt_sub_passed_finals spf        ON (t.task = spf.task)
             LEFT OUTER JOIN cnt_sub_failed_finals sff        ON (t.task = sff.task)
             LEFT OUTER JOIN cnt_sub_latest_not_accepted slna ON (t.task = slna.task)
             LEFT OUTER JOIN rh_count_uploads_all u           ON (t.task = u.task)
             LEFT OUTER JOIN rh_count_uploads_accepted ua     ON (t.task = ua.task)
             LEFT OUTER JOIN rh_count_uploads_rejected ur     ON (t.task = ur.task)
             LEFT OUTER JOIN avg_finals_passed fpavg          ON (t.task = fpavg.task)
             LEFT OUTER JOIN q0_finals_passed fpq0            ON (t.task = fpq0.task)
             LEFT OUTER JOIN q1_finals_passed fpq1            ON (t.task = fpq1.task)
             LEFT OUTER JOIN q2_finals_passed fpq2            ON (t.task = fpq2.task)
             LEFT OUTER JOIN q3_finals_passed fpq3            ON (t.task = fpq3.task)
             LEFT OUTER JOIN q4_finals_passed fpq4            ON (t.task = fpq4.task)
             LEFT OUTER JOIN avg_finals_failed ffavg          ON (t.task = ffavg.task)
             LEFT OUTER JOIN q0_finals_failed ffq0            ON (t.task = ffq0.task)
             LEFT OUTER JOIN q1_finals_failed ffq1            ON (t.task = ffq1.task)
             LEFT OUTER JOIN q2_finals_failed ffq2            ON (t.task = ffq2.task)
             LEFT OUTER JOIN q3_finals_failed ffq3            ON (t.task = ffq3.task)
             LEFT OUTER JOIN q4_finals_failed ffq4            ON (t.task = ffq4.task)
             LEFT OUTER JOIN avg_only_failed ofavg            ON (t.task = ofavg.task)
             LEFT OUTER JOIN q0_only_failed  ofq0             ON (t.task = ofq0.task)
             LEFT OUTER JOIN q1_only_failed  ofq1             ON (t.task = ofq1.task)
             LEFT OUTER JOIN q2_only_failed  ofq2             ON (t.task = ofq2.task)
             LEFT OUTER JOIN q3_only_failed  ofq3             ON (t.task = ofq3.task)
             LEFT OUTER JOIN q4_only_failed  ofq4             ON (t.task = ofq4.task)
        ;
--   Syntax via Dummy
--
--
--        rh_boxplot_datatabular AS
--        ( SELECT task.id as typ, value
--          FROM task t, solution s
--          WHERE t.id = s.taskid
--        ) ,
--        sortedPartition AS
--        ( SELECT typ, value, ROW_NUMBER() OVER(PARTITION BY o.typ ORDER BY o.value) as Reihung
--          FROM rh_boxplot_datatabular o
--        ) ,
--        maxGroupElement AS
--        (SELECT typ, max(sP.Reihung) as maxElement
--        FROM sortedPartition sP
--        Group By typ
--        ),
--        q0 AS (
--        Select s.typ, min(s.value) as q0
--        FROM sortedPartition s
--        GROUP BY s.typ
--        ) ,
--        q1 AS (
--        SELECT s.typ, max(s.value) as q1
--        FROM sortedPartition s, maxGroupElement m
--        WHERE s.Reihung <= (0.25 * m.maxElement) AND s.typ = m.typ
--        Group By s.typ
--        ) ,
--        q2 AS (
--        SELECT s.typ, max(s.value) as q2
--        FROM sortedPartition s, maxGroupElement m
--        WHERE s.Reihung <= (0.5 * m.maxElement) AND s.typ = m.typ
--        Group By s.typ
--        ) ,
--        q3 AS (
--        SELECT s.typ, max(s.value) as q3
--        FROM sortedPartition s, maxGroupElement m
--        WHERE s.Reihung <= (0.75 * m.maxElement) AND s.typ = m.typ
--        Group By s.typ
--        ) ,
--        q4 AS (
--        Select s.typ, max(s.value) as q4
--        FROM sortedPartition s
--        GROUP BY s.typ
--        )
--        CREATE OR REPLACE VIEW tasksstatistic AS
--        Select q0.typ, q0.q0,q1.q1,q2.q2,q3.q3,q4.q4
--        From q0, q1, q2, q3, q4
--        WHERE q0.typ = q1.typ
--        AND   q0.typ = q2.typ
--        AND   q0.typ = q3.typ
--        AND   q0.typ = q4.typ ;
          """


    db_engine = settings.DATABASES['default']['ENGINE']
    sql = (sql_begin_oracle + sql_rest) if "oracle" in db_engine else (sql_begin_other + sql_rest)

    # first we need to run the raw SQL statements to create the database view dbview_tasksstatistic
    # and than we can connect the Django Model TasksStatistic to the dbview_tasksstatistic.
    operations = [
        migrations.RunSQL(
	  sql
	),
        migrations.CreateModel(
            name='TasksStatistic',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('task', models.ForeignKey(verbose_name='Task', to='tasks.Task', on_delete=models.DO_NOTHING)),
                ('title', models.CharField(help_text='The name of the Task', max_length=100)),
                ('submitters_all', models.BigIntegerField()),
                ('submitters_passed_finals', models.BigIntegerField()),
                ('submitters_failed_finals', models.BigIntegerField()),
                ('submitters_latest_not_accepted', models.BigIntegerField()),
                ('uploads_all', models.BigIntegerField()),
                ('uploads_accepted', models.BigIntegerField()),
                ('uploads_rejected', models.BigIntegerField()),
                ('avg_upl_until_final_pass', models.BigIntegerField(verbose_name='avg uploads until final passed')),
                ('lo_whisker_upl_til_final_pass', models.BigIntegerField(verbose_name='lower whisker uploads until final passed')),
                ('lo_quart_upl_til_final_pass', models.BigIntegerField(verbose_name='lower quartiel uploads until final passed')),
                ('med_upl_til_final_pass', models.BigIntegerField(verbose_name='median uploads until final passed')),
                ('up_quart_upl_til_final_pass', models.BigIntegerField(verbose_name='upper quartiel uploads until final passed')),
                ('up_whisker_upl_until_final_pass', models.BigIntegerField(verbose_name='upper whisker uploads until final passed')),
                ('avg_uploads_final_failed', models.BigIntegerField()),
                ('lo_whisker_upl_final_fail', models.BigIntegerField(verbose_name='lower whisker uploads final failed')),
                ('lo_quart_upl_final_fail', models.BigIntegerField(verbose_name='lower quartiel uploads final failed')),
                ('median_uploads_final_failed', models.BigIntegerField()),
                ('up_quart_upl_final_failed', models.BigIntegerField(verbose_name='upper quartiel uploads final failed')),
                ('up_whisker_upl_final_failed', models.BigIntegerField(verbose_name='upper whisker uploads final failed')),
                ('avg_uploads_only_failed', models.BigIntegerField()),
                ('lo_whisker_upl_only_fail', models.BigIntegerField(verbose_name='lower whisker uploads only failed')),
                ('lo_quart_upl_only_fail', models.BigIntegerField(verbose_name='lower quartiel uploads only failed')),
                ('median_uploads_only_failed', models.BigIntegerField()),
                ('up_quart_upl_only_failed', models.BigIntegerField(verbose_name='upper quartiel uploads only failed')),
                ('up_whisker_upl_only_failed', models.BigIntegerField(verbose_name='upper whisker uploads only failed')),
            ],
            options={
                'db_table': 'dbview_tasksstatistic',
                'managed': False,
            },
        ),
    ]
