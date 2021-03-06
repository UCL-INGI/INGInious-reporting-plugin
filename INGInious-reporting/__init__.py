#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#   @author 2019 Ludovic Taffin
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

#   Reporting plugin for INGInious
import json
import os
import logging

from flask import send_from_directory, request
from inginious.frontend.pages.utils import INGIniousPage
from inginious.frontend.pages.course_admin.utils import INGIniousSubmissionsAdminPage

""" A plugin that displays beautiful reporting widgets """

PATH_TO_PLUGIN = os.path.abspath(os.path.dirname(__file__))


def add_admin_menu(course):  # pylint: disable=unused-argument
    """ Add a menu for jplag analyze in the administration """
    return 'reporting', '<i class="fa fa-bar-chart"></i>&nbsp; Reporting'


class StaticMockPage(INGIniousPage):
    def GET(self, path):
        return send_from_directory(os.path.join(PATH_TO_PLUGIN, "static"), path)

    def POST(self, path):
        return self.GET(path)


def init(plugin_manager, _, _2, config):
    """ Init the plugin """
    netv4 = config.get('networkv4')
    netv6 = config.get('networkv6')
    netname = config.get('networkname')

    def _clean_data(data):
        cleaned = data.replace("&#39;", "")
        cleaned = cleaned.replace("[", "")
        cleaned = cleaned.replace("]", "")
        cleaned = cleaned.replace(" ", "")
        cleaned = cleaned.split(",")
        return cleaned

    class ReportingPage(INGIniousSubmissionsAdminPage):
        """Page to allow user choose students and tasks from the course and then display a report diagram"""

        def GET_AUTH(self, courseid):  # pylint: disable=arguments-differ
            """ GET request """
            course = self.course_factory.get_course(courseid)

            user_input = request.form.copy()
            user_input["users"] = request.form.getlist("users")
            user_input["audiences"] = request.form.getlist("audiences")
            user_input["tasks"] = request.form.getlist("tasks")
            user_input["org_tags"] = request.form.getlist("org_tags")

            params = self.get_input_params(user_input, course, 500)
            return self.show_page(course, params)

        def POST_AUTH(self, courseid):
            """POST REQUEST - Allows display of the diagram"""
            self._logger = logging.getLogger("inginious.webapp.plugins.reporting")
            course = self.course_factory.get_course(courseid)
            tasks = course.get_tasks()

            x = request.form.copy()
            x["tasks"] = request.form.getlist("tasks")
            x["users"] = request.form.getlist("users")

            student_ids = str(x["users"]).encode("ascii").decode()
            task_ids = ",".join(x["tasks"])
            task_titles = {}
            for task_id in tasks:
                task_titles[task_id] = tasks[task_id].get_name(self.user_manager.session_language())
            return self.template_helper.render("reporting_chart.html", template_folder=PATH_TO_PLUGIN + "/templates/",
                                               course=course, stud_ids=student_ids, task_ids=task_ids,
                                               task_titles=task_titles, netname=netname)

        def show_page(self, course, user_input, msg="", error=False):
            # Load task list
            # tasks, user_data, aggregations, tutored_aggregations, \
            # tutored_users, checked_tasks, checked_users, show_aggregations = self.show_page_params(course, user_input)
            users, tutored_users, audiences, tutored_audiences, tasks, limit = self.get_course_params(course,
                                                                                                      user_input)

            return self.template_helper.render("reporting_index.html", template_folder=PATH_TO_PLUGIN + "/templates/",
                                               course=course, tasks=tasks, users=users, audiences=audiences,
                                               tutored_audiences=tutored_audiences, tutored_users=tutored_users,
                                               old_params=user_input, msg=msg, error=error)

    class Diagram1Page(INGIniousSubmissionsAdminPage):
        ### GET/POST ###
        def POST(self, courseid):
            self._logger = logging.getLogger("inginious.webapp.plugins.reporting")
            dicgrade = {}
            data = request.form
            student_ids = _clean_data(data["student_ids"])
            task_ids = _clean_data(data["task_ids"])
            evaluated_submissions = {}
            for task_id in task_ids:
                evaluated_submissions[task_id] = []

            def students_per_grade(grades_per_tasks):
                for key, value in grades_per_tasks.items():
                    dicgrade[key] = {}
                    for grade in value:
                        grade = float(grade) / 5
                        grade = round(grade * 2) * 0.5
                        if grade not in dicgrade[key]:
                            dicgrade[key][grade] = 1
                        else:
                            dicgrade[key][grade] = dicgrade[key][grade] + 1
                return dicgrade

            if student_ids == ['']:
                student_ids = (self.database.aggregations.find_one({"courseid": courseid}, {"students": 1}))
                student_ids = student_ids["students"]

            subs = list(self.database.submissions.aggregate(
                [
                    {
                        "$match": {"$and": [
                            {"taskid": {"$in": task_ids}, "username": {"$in": student_ids}, "courseid": courseid}]}
                    },
                    {
                        "$group":
                            {
                                "_id": {
                                    "username": "$username",
                                    "taskid": "$taskid",
                                    "courseid": "$courseid"
                                },
                                "grade": {"$last": "$grade"},
                                "submitted_on": {"$last": "$submitted_on"}
                            }
                    }
                ]
            ))
            for sub in subs:
                evaluated_submissions[sub["_id"]["taskid"]].append(sub["grade"])

            table_stud_per_grade = students_per_grade(evaluated_submissions)
            return json.dumps(table_stud_per_grade)

    class Diagram2Page(INGIniousSubmissionsAdminPage):
        ### GET/POST ###
        def POST(self, courseid):
            course = self.course_factory.get_course(courseid)
            self._logger = logging.getLogger("inginious.webapp.plugins.reporting")
            data = request.form
            task_ids = _clean_data(data["task_ids"])
            tasks_data = {}
            tasks_data["nstuds"] = len(self.user_manager.get_course_registered_users(course, False))
            for task_id in task_ids:
                data = list(self.database.user_tasks.aggregate(
                    [
                        {
                            "$match":
                                {
                                    "courseid": courseid,
                                    "taskid": task_id,
                                    "username": {"$in": self.user_manager.get_course_registered_users(course, False)}
                                }
                        },
                        {
                            "$group":
                                {
                                    "_id": "$taskid",
                                    "viewed": {"$sum": 1},
                                    "attempted": {"$sum": {"$cond": [{"$ne": ["$tried", 0]}, 1, 0]}},
                                    "succeeded": {"$sum": {"$cond": ["$succeeded", 1, 0]}}
                                }
                        }
                    ]))
                tasks_data[task_id] = data
            return json.dumps(tasks_data)

    class Diagram3Page(INGIniousSubmissionsAdminPage):
        ### HELPERS ###
        def _per_task_submission_count_and_grade(self, username, courseid, tasks):
            task_count_sub = {}
            total = 0
            nb_task_tried = 0
            for task in tasks:
                submissions = self.database.submissions.find({"username": str(username),
                                                              "taskid": task,
                                                              "courseid": courseid})
                ut = self.database.user_tasks.find_one({"username": username, "taskid": task, "courseid": courseid})
                grade = ut["grade"] if ut is not None else 0
                task_count_sub[task] = {"count": submissions.count(), "grade": grade}
                total += grade
                if submissions.count() > 0:
                    nb_task_tried += 1
            return task_count_sub, total, nb_task_tried

        ### GET/POST ###
        def POST(self, courseid):
            data = request.form
            task_ids = _clean_data(data["task_ids"])
            student_ids = _clean_data(data["student_ids"])
            course = self.course_factory.get_course(courseid)
            students = self.user_manager.get_course_registered_users(course, False)
            # get number of submissions per student per task
            users_submissions = {}
            for student in list(set(student_ids).intersection(students)):
                users_submissions[student] = {}
                users_submissions[student]["tasks"], total, nb_task_tried = self._per_task_submission_count_and_grade(
                    student,
                    courseid, task_ids)
                nb_task = len(users_submissions[student]["tasks"])
                users_submissions[student]["total"] = int(total / nb_task)
                users_submissions[student]["nb_task"] = nb_task_tried
                first = list(self.database.submissions.find({"courseid": courseid, "username": student}).sort(
                    [('submitted_on', -1)]).limit(1))
                first = first[0] if len(first) > 0 else None
                last = list(self.database.submissions.find({"courseid": courseid, "username": student}).sort(
                    [('submitted_on', 1)]).limit(1))
                last = last[0] if len(last) > 0 else None
                if first is not None and last is not None:
                    delta = abs((first["submitted_on"] - last["submitted_on"]))
                    users_submissions[student]["course_time"] = {"days": int(delta.days),
                                                                 "hours": int(delta.seconds / 3600),
                                                                 "minutes": int((delta.seconds % 3600) / 60),
                                                                 "seconds": int((delta.seconds % 3600) % 60)}
                else:
                    users_submissions[student]["course_time"] = {"days": 0, "hours": 0, "minutes": 0, "seconds": 0}
            return json.dumps(users_submissions)

    class Diagram4Page(INGIniousSubmissionsAdminPage):
        ### HELPERS ###

        ### GET/POST ###
        def POST(self, courseid):
            per_ip_username = {}
            per_username_ip_and_q = {}
            username_ip = {}
            data = request.form
            task_ids = _clean_data(data["task_ids"])
            student_ids = _clean_data(data["student_ids"])
            submissions = list(self.database.submissions.find({"taskid": {"$in": task_ids},
                                                               "username": {"$in": student_ids},
                                                               "courseid": courseid}))
            sort_per_username_ip_and_q = {}
            for sub in submissions:
                cur_date = sub["submitted_on"].strftime("%d/%m/%Y %H:%M:%S")
                cur_username = sub["username"][0]
                cur_task_id = sub["taskid"]
                if "user_ip" in sub:
                    # SECTION 1
                    cur_ip = sub["user_ip"]

                    if cur_ip in per_ip_username and cur_username not in per_ip_username[cur_ip]:
                        per_ip_username[cur_ip].append(cur_username)
                    elif cur_ip not in per_ip_username:
                        per_ip_username[cur_ip] = [cur_username]
                    else:
                        pass
                    # SECTION 2
                    if cur_username not in per_username_ip_and_q:
                        per_username_ip_and_q[cur_username] = {cur_ip: {cur_task_id: [cur_date]}}
                    elif cur_username in per_username_ip_and_q and cur_ip not in per_username_ip_and_q[cur_username]:
                        per_username_ip_and_q[cur_username][cur_ip] = {cur_task_id: [cur_date]}
                    elif cur_username in per_username_ip_and_q and \
                            cur_ip in per_username_ip_and_q[cur_username] and \
                            cur_task_id not in [x for x in per_username_ip_and_q[cur_username][cur_ip]]:
                        per_username_ip_and_q[cur_username][cur_ip][cur_task_id] = [cur_date]
                    else:
                        per_username_ip_and_q[cur_username][cur_ip][cur_task_id].append(cur_date)
                    if (len(per_username_ip_and_q[cur_username])) > 1:
                        sort_per_username_ip_and_q[cur_username] = per_username_ip_and_q[cur_username].copy()
                    # SECTION 3
                    # check if an address is in given network
                    import ipaddress
                    an_address = ipaddress.ip_address(cur_ip)
                    try:
                        a_network = ipaddress.ip_network(netv4)
                    except ValueError:
                        a_network = ipaddress.ip_network(netv4, strict=False)
                    address_in_network_v4 = an_address in a_network
                    try:
                        a_network = ipaddress.ip_network(netv6)
                    except ValueError:
                        a_network = ipaddress.ip_network(netv6, strict=False)
                    address_in_network_v6 = an_address in a_network
                    if cur_username not in username_ip:
                        username_ip[cur_username] = [
                            {"ip": cur_ip, "in_v4": address_in_network_v4, "in_v6": address_in_network_v6}]
                    elif cur_username in username_ip and cur_ip not in [sub['ip'] for sub in username_ip[cur_username]]:
                        username_ip[cur_username].append(
                            {"ip": cur_ip, "in_v4": address_in_network_v4, "in_v6": address_in_network_v6})
                    else:
                       pass

            final_per_ip_username = {}
            for elem in per_ip_username:
                if len(per_ip_username[elem]) > 1:
                    final_per_ip_username[elem] = per_ip_username[elem].copy()
            return json.dumps(
                {"section1": final_per_ip_username, "section2": sort_per_username_ip_and_q, "section3": username_ip})

    plugin_manager.add_page('/plugins/reporting/static/<path:path>', StaticMockPage.as_view("reportingstaticpage"))
    plugin_manager.add_hook("javascript_header", lambda: "/static/js/libs/chart.min.js")
    plugin_manager.add_hook("javascript_header", lambda: "/plugins/reporting/static/chartjs-plugin-annotation.min.js")
    plugin_manager.add_page("/admin/<courseid>/reporting", ReportingPage.as_view("reportingpage"))
    plugin_manager.add_page("/admin/<courseid>/reporting/diag1", Diagram1Page.as_view("reportingdiag1page"))
    plugin_manager.add_page("/admin/<courseid>/reporting/diag2", Diagram2Page.as_view("reportingdiag2page"))
    plugin_manager.add_page("/admin/<courseid>/reporting/diag3", Diagram3Page.as_view("reportingdiag3page"))
    plugin_manager.add_page("/admin/<courseid>/reporting/diag4", Diagram4Page.as_view("reportingdiag4page"))
    plugin_manager.add_hook('course_admin_menu', add_admin_menu)
