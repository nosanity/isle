module.exports = function (grunt) {
	grunt.initConfig({
		pkg    : grunt.file.readJSON('package.json'),
		clean  : {
			options : {
				force : true
			},
			js      : [ '<%= pkg.webpath %>/js/*.js' ],
			css     : [ '<%= pkg.webpath %>/css/*.css' ],
			font    : [ '<%= pkg.webpath %>/font/**/*' ],
			img     : [ '<%= pkg.webpath %>/img/**/*' ]
		},
		copy   : {
			js   : {
				files : [
					{
						expand  : true,
						flatten : true,
						src     : [
							'node_modules/jquery/dist/jquery.min.js',
							'node_modules/popper.js/dist/umd/popper.min.js',
							'node_modules/bootstrap/dist/js/bootstrap.min.js',
							'node_modules/bootstrap-confirmation2/dist/bootstrap-confirmation.min.js'
						],
						dest    : '<%= pkg.webpath %>/js/',
						filter  : 'isFile'
					}
				]
			},
			font : {
				files : [
					{
						expand  : true,
						flatten : true,
						src     : [ 'node_modules/font-awesome/fonts/*' ],
						dest    : '<%= pkg.webpath %>/font/font-awesome/',
						filter  : 'isFile'
					},
					{
						expand  : true,
						flatten : true,
						src     : [ 'font/OpenSans/*' ],
						dest    : '<%= pkg.webpath %>/font/opensans/',
						filter  : 'isFile'
					}
				]
			},
			img  : {
				files : [
					{
						expand  : true,
						flatten : true,
						src     : [ 'img/*' ],
						dest    : '<%= pkg.webpath %>/img/',
						filter  : 'isFile'
					}
				]
			}
		},
		sass   : {
			app         : {
				options : '<%= pkg.scss %>',
				files   : { '<%= pkg.webpath %>/css/app.min.css' : 'scss/app.scss' }
			},
			bootstrap   : {
				options : '<%= pkg.scss %>',
				files   : { '<%= pkg.webpath %>/css/bootstrap.min.css' : 'scss/bootstrap/bootstrap.scss' }
			},
			fontawesome : {
				options : '<%= pkg.scss %>',
				files   : { '<%= pkg.webpath %>/css/font-awesome.min.css' : 'scss/font-awesome/font-awesome.scss' }
			}
		},
		uglify : {
			app     : {
				src  : 'js/app.js',
				dest : '<%= pkg.webpath %>/js/app.min.js'
			},
			file_upload     : {
				src  : 'js/file-upload.js',
				dest : '<%= pkg.webpath %>/js/file-upload.min.js'
			}
		},
		watch  : {
			app       : {
				files : [ 'scss/*.scss' ],
				tasks : [ 'sass:app' ]
			},
			bootstrap : {
				files : [ 'scss/bootstrap/*.scss' ],
				tasks : [ 'sass:bootstrap' ]
			},
			js        : {
				files : [ 'js/app.js' ],
				tasks : [ 'uglify:app' ]
			},
			js_fu        : {
				files : [ 'js/file-upload.js' ],
				tasks : [ 'uglify:file_upload' ]
			},
			img       : {
				files : [ 'img/**/*' ],
				tasks : [ 'copy:img' ]
			}
		}
	});

	grunt.loadNpmTasks('grunt-contrib-clean');
	grunt.loadNpmTasks('grunt-contrib-copy');
	grunt.loadNpmTasks('grunt-contrib-sass');
	grunt.loadNpmTasks('grunt-contrib-uglify');
	grunt.loadNpmTasks('grunt-contrib-watch');

	grunt.registerTask('default', [ 'sass', 'copy', 'uglify', 'watch' ]);
	grunt.registerTask('production', [ 'clean', 'sass', 'copy', 'uglify' ]);
};
